import asyncio
import json
import requests
from google import genai
from google.genai import types

from core import audio_playback
from core.tas_voices import (
    normalize_voice,
    DEFAULT_TAS_VOICE,
    TAS_STREAM_AUDIO_FORMAT,
)

OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"


def _empty_usage():
    return {"input": 0, "output": 0}


def _google_usage(resp):
    """Google reports usage on the response object rather than in the payload."""
    meta = getattr(resp, "usage_metadata", None)
    if not meta:
        return _empty_usage()
    return {
        "input": getattr(meta, "prompt_token_count", 0) or 0,
        "output": getattr(meta, "candidates_token_count", 0) or 0,
    }


class ZaniBrain:
    def __init__(self, api_key, model_name, provider="google"):
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.tas_enabled = False
        self.tas_voice = DEFAULT_TAS_VOICE
        self.text_model_fallback = model_name

        if self.provider == "google":
            self.client = genai.Client(api_key=api_key)

    async def llm_api_caller(self, system_prompt, history, tools):
        """
        Unified API caller for MCP Orchestrator.
        Returns a dict: {"content": str, "tool_calls": [{"id": str, "function": {"name": str, "arguments": str}}]}
        """
        if self.provider == "openrouter":
            return await asyncio.to_thread(self._call_openrouter, system_prompt, history, tools)
        else:
            return await asyncio.to_thread(self._call_google, system_prompt, history, tools)

    def _openrouter_messages(self, system_prompt, history):
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            role = h["role"]
            if role == "tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": h.get("tool_call_id", ""),
                    "name": h.get("name", ""),
                    "content": h.get("content", "")
                })
            else:
                msg = {"role": "assistant" if role == "assistant" else "user", "content": h.get("content", "")}
                if h.get("tool_calls"):
                    msg["tool_calls"] = h["tool_calls"]
                messages.append(msg)
        return messages

    def _openrouter_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _tas_audio_ok(self) -> bool:
        return self.tas_enabled and audio_playback.playback_ready()

    def _call_openrouter(self, system_prompt, history, tools):
        messages = self._openrouter_messages(system_prompt, history)
        if self._tas_audio_ok():
            return self._call_openrouter_tas_stream(messages, tools)

        model = self.model_name
        if self.tas_enabled and not audio_playback.playback_ready():
            model = self.text_model_fallback or model

        return self._call_openrouter_plain(messages, tools, model=model)

    def _call_openrouter_plain(self, messages, tools, model: str | None = None):
        data = {
            "model": model or self.model_name,
            "messages": messages,
            "reasoning": {"enabled": True},
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        resp = requests.post(
            url=OPENROUTER_CHAT,
            headers=self._openrouter_headers(),
            data=json.dumps(data),
            timeout=120,
        )
        resp_json = resp.json()

        if "error" in resp_json:
            return {
                "content": f"Error: {resp_json['error']}",
                "tool_calls": [],
                "usage": _empty_usage(),
                "error": resp_json["error"],
                "tas_audio_skipped": self.tas_enabled,
            }

        usage_raw = resp_json.get("usage") or {}
        message = resp_json["choices"][0]["message"]

        return {
            "content": message.get("content", "") or "",
            "tool_calls": message.get("tool_calls", []),
            "usage": {
                "input": usage_raw.get("prompt_tokens", 0) or 0,
                "output": usage_raw.get("completion_tokens", 0) or 0,
            },
            "tas_audio_skipped": self.tas_enabled and not self._tas_audio_ok(),
        }

    def _call_openrouter_tas_stream(self, messages, tools):
        voice = normalize_voice(self.tas_voice)
        data = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "modalities": ["text", "audio"],
            "audio": {"voice": voice, "format": TAS_STREAM_AUDIO_FORMAT},
        }
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        resp = requests.post(
            url=OPENROUTER_CHAT,
            headers=self._openrouter_headers(),
            data=json.dumps(data),
            stream=True,
            timeout=180,
        )
        if resp.status_code != 200:
            try:
                err = resp.json()
            except Exception:
                err = resp.text[:500]
            return {
                "content": f"Error: {err}",
                "tool_calls": [],
                "usage": _empty_usage(),
                "error": err,
            }

        content_parts: list[str] = []
        audio_chunks: list[str] = []
        tool_calls: dict[int, dict] = {}
        usage = _empty_usage()

        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            payload = raw[6:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                return {
                    "content": f"Error: {err}",
                    "tool_calls": [],
                    "usage": _empty_usage(),
                    "error": err,
                }
            if chunk.get("usage"):
                u = chunk["usage"]
                usage = {
                    "input": u.get("prompt_tokens", 0) or 0,
                    "output": u.get("completion_tokens", 0) or 0,
                }
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            audio = delta.get("audio") or {}
            if audio.get("data"):
                audio_chunks.append(audio["data"])
            if audio.get("transcript"):
                content_parts.append(audio["transcript"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(
                    idx,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]

        merged_tools = [tool_calls[i] for i in sorted(tool_calls)]
        audio_b64 = ""
        if merged_tools:
            audio_chunks = []
        elif audio_chunks:
            audio_b64 = "".join(audio_chunks)

        return {
            "content": "".join(content_parts).strip(),
            "tool_calls": merged_tools,
            "usage": usage,
            "audio_b64": audio_b64,
            "tas_audio_skipped": False,
        }

    def _call_google(self, system_prompt, history, tools):
        # Build google tools array
        google_tools = []
        if tools:
            funcs = []
            for t in tools:
                f = t["function"]
                # Convert dict to types.FunctionDeclaration
                funcs.append(types.FunctionDeclaration(
                    name=f["name"],
                    description=f.get("description", ""),
                    parameters=f.get("parameters", {})
                ))
            if funcs:
                google_tools = [types.Tool(function_declarations=funcs)]

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=google_tools if google_tools else None
        )

        prepared = []
        for h in history:
            role = h["role"]
            if role == "tool":
                # Google format for tool results
                call_res = types.FunctionResponse(
                    name=h.get("name", ""),
                    response={"result": h.get("content", "")}
                )
                prepared.append(types.Content(role="user", parts=[types.Part.from_function_response(call_res)]))
            else:
                r = "model" if role == "assistant" else "user"
                parts = []
                if h.get("content"):
                    parts.append(types.Part.from_text(h["content"]))
                
                if h.get("tool_calls"):
                    for tc in h["tool_calls"]:
                        f = tc["function"]
                        args = f["arguments"]
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                args = {}
                        parts.append(types.Part.from_function_call(
                            name=f["name"],
                            args=args
                        ))
                
                if parts:
                    prepared.append(types.Content(role=r, parts=parts))

        # Send to Google
        resp = self.client.models.generate_content(
            model=self.model_name,
            contents=prepared,
            config=config
        )

        # Parse response back to our unified format
        result = {"content": "", "tool_calls": [], "usage": _google_usage(resp)}
        if not resp.candidates:
            return result

        content = resp.candidates[0].content
        if not content or not content.parts:
            return result

        for index, part in enumerate(content.parts):
            if part.text:
                result["content"] += part.text + "\n"
            elif part.function_call:
                # Add to tool calls. Google issues no ids of its own, so we mint
                # one per part — a shared id would collapse several calls onto a
                # single tool_call_id and lose all but the last result.
                result["tool_calls"].append({
                    "id": f"google_req_{index}",
                    "function": {
                        "name": part.function_call.name,
                        "arguments": json.dumps(part.function_call.args)
                    }
                })

        result["content"] = result["content"].strip()
        return result
