"""
Optional speech for Zani, via Kokoro on OpenRouter.

Off unless switched on. Every spoken line is a billed API call and a couple of
seconds of latency, so this never starts itself — `/tts on` or ctrl+s, and the
state is remembered per project.

Three things the endpoint does that a "swap the base URL" port of an OpenAI TTS
script would get wrong:

`response_format` must be sent. The default is a PCM stream that does not
terminate — a plain request sits open and returns nothing at all. Only "mp3"
and "pcm" are accepted; "wav" is a 400.

Generation runs about twice realtime, so it must never touch the UI thread.
Synthesis and playback happen on a worker, and a second request while one is
still speaking replaces it rather than queueing a backlog.

What reaches the API is prose only. Code blocks, paths and markup are stripped
first — reading a traceback aloud is worthless and costs the same per character
as reading a sentence.
"""

import os
import re
import shutil
import subprocess
import tempfile

import requests

ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "hexgrad/kokoro-82m"

# Clear and composed, which survives 24kHz mono better than a breathy voice —
# consonants in identifiers like NameResolutionError have to stay intelligible.
VOICE = "af_sky"

# Roughly a paragraph. Long enough for a real answer, short enough that a wall
# of text does not turn into a minute of audio nobody asked for.
MAX_CHARS = 600
TIMEOUT = 45

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`]*`")
_PATHY = re.compile(r"\S*[/\\]\S*")
_MARKUP = re.compile(r"[*_#>\[\]|]+")
_RUNS = re.compile(r"\s+")

PLAYERS = (
    ("mpv", ["--no-video", "--really-quiet", "--"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("mpg123", ["-q"]),
)


def spoken_form(text):
    """
    Reduce a reply to the part worth hearing.

    Fenced code, inline code and anything path-shaped are dropped rather than
    spelled out. What remains is the prose, capped — the cap is on characters
    because that is exactly what the API bills for.
    """
    if not text:
        return ""
    text = _FENCE.sub(" ", text)
    text = _INLINE.sub(" ", text)
    text = _PATHY.sub(" ", text)
    text = _MARKUP.sub(" ", text)
    text = _RUNS.sub(" ", text).strip()

    if len(text) <= MAX_CHARS:
        return text
    # Prefer to stop on a sentence rather than mid-word.
    clipped = text[:MAX_CHARS]
    stop = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    return clipped[:stop + 1] if stop > MAX_CHARS // 2 else clipped


def player_command():
    for name, args in PLAYERS:
        path = shutil.which(name)
        if path:
            return [path, *args]
    return None


def available():
    return player_command() is not None


class Speaker:
    """Synthesises and plays one line at a time; a new line pre-empts the old."""

    def __init__(self, api_key, voice=VOICE):
        self.api_key = api_key
        self.voice = voice
        self.enabled = False
        self._process = None
        self.last_error = None

    def stop(self):
        """Silence whatever is playing. Safe to call when nothing is."""
        process, self._process = self._process, None
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def speak(self, text):
        """
        Blocking: synthesise and play. Callers run this off the UI thread.

        Returns None on success, or a short reason it did not speak — the
        caller surfaces that once rather than failing silently.
        """
        if not self.enabled:
            return None

        line = spoken_form(text)
        if not line:
            return None

        command = player_command()
        if command is None:
            return "no audio player found (install mpv, ffplay or mpg123)"

        try:
            response = requests.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "voice": self.voice,
                    "input": line,
                    # Required. Without it the API streams PCM that never ends.
                    "response_format": "mp3",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as error:
            return f"speech request failed: {type(error).__name__}"

        if response.status_code != 200 or not response.content:
            return f"speech api returned {response.status_code}"

        handle = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            handle.write(response.content)
            handle.close()
            self.stop()
            self._process = subprocess.Popen(
                [*command, handle.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._process.wait()
        except Exception as error:
            return f"playback failed: {type(error).__name__}"
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
        return None
