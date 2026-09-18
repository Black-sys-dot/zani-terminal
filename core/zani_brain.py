import asyncio
import json
import requests
from google import genai
from google.genai import types


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

    def _call_openrouter(self, system_prompt, history, tools):
        messages = [{"role": "system", "content": system_prompt}]
        
        # Translate history format
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

        data = {
            "model": self.model_name,
            "messages": messages,
            "reasoning": {"enabled": True},
        }

        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"

        resp = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(data)
        )
        resp_json = resp.json()

        if "error" in resp_json:
            return {
                "content": f"Error: {resp_json['error']}",
                "tool_calls": [],
                "usage": _empty_usage(),
                "error": resp_json["error"],
            }

        usage_raw = resp_json.get("usage") or {}
        message = resp_json["choices"][0]["message"]

        return {
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls", []),
            "usage": {
                "input": usage_raw.get("prompt_tokens", 0) or 0,
                "output": usage_raw.get("completion_tokens", 0) or 0,
            },
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
