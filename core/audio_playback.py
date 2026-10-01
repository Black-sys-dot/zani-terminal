"""Play TaS PCM audio (WAV container). Prefer paplay when Pulse is forwarded from the host."""

import base64
import os
import shutil
import struct
import subprocess
import tempfile
import time

from core.tas_voices import TAS_PCM_CHANNELS, TAS_PCM_SAMPLE_RATE

_PCM_RATES = (TAS_PCM_SAMPLE_RATE, 16000, 22050, 44100, 48000)

_READY_CACHE: tuple[bool, float] | None = None
_READY_CACHE_TTL = 45.0


def in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _pcm16_to_wav(pcm: bytes, rate: int, channels: int = TAS_PCM_CHANNELS) -> bytes:
    bits = 16
    byte_rate = rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_size,
    )
    return header + pcm


def _pulse_configured() -> bool:
    return bool(os.environ.get("PULSE_SERVER"))


def _pactl_path() -> str | None:
    return shutil.which("pactl")


def _paplay_path() -> str | None:
    return shutil.which("paplay")


def _mpv_path() -> str | None:
    return shutil.which("mpv")


def available() -> bool:
    if _pulse_configured() and (_pactl_path() or _paplay_path()):
        return True
    return bool(_mpv_path() or shutil.which("ffplay"))


def _probe_wav_play(path: str, *, ao: str) -> bool:
    mpv = _mpv_path()
    if not mpv:
        return False
    proc = subprocess.run(
        [mpv, "--no-video", "--really-quiet", f"--ao={ao}", "--length=0.05", path],
        capture_output=True,
        timeout=10,
    )
    return proc.returncode == 0


def invalidate_playback_ready_cache() -> None:
    global _READY_CACHE
    _READY_CACHE = None


def playback_ready(*, force: bool = False) -> bool:
    """
    True when we can reach host audio (Pulse and/or ALSA). False in plain Docker → TaS stays muted.
    Result is cached briefly — probing runs pactl/mpv and must not run on every UI frame.
    """
    global _READY_CACHE
    now = time.monotonic()
    if not force and _READY_CACHE is not None and now - _READY_CACHE[1] < _READY_CACHE_TTL:
        return _READY_CACHE[0]

    tone = _pcm16_to_wav(b"\x00\x00" * 480, TAS_PCM_SAMPLE_RATE)
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        handle.write(tone)
        handle.close()
        if _pulse_configured():
            pactl = _pactl_path()
            if pactl and subprocess.run([pactl, "info"], capture_output=True, timeout=5).returncode == 0:
                if _probe_wav_play(handle.name, ao="pulse"):
                    _READY_CACHE = (True, now)
                    return True
        if os.path.isdir("/dev/snd"):
            if _probe_wav_play(handle.name, ao="alsa"):
                _READY_CACHE = (True, now)
                return True
        _READY_CACHE = (False, now)
        return False
    except Exception:
        _READY_CACHE = (False, now)
        return False
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def _play_wav_file(path: str) -> str | None:
    paplay = _paplay_path()
    if paplay and _pulse_configured():
        proc = subprocess.run(
            [paplay, path],
            capture_output=True,
            timeout=180,
        )
        if proc.returncode == 0:
            return None
        err = (proc.stderr or b"").decode(errors="replace").strip()[-240:]
        if err:
            return f"paplay: {err}"

    mpv = _mpv_path()
    if mpv:
        for ao in ("pulse", "alsa"):
            if ao == "pulse" and not _pulse_configured():
                continue
            if ao == "alsa" and not os.path.isdir("/dev/snd"):
                continue
            proc = subprocess.run(
                [mpv, "--no-video", "--really-quiet", f"--ao={ao}", path],
                capture_output=True,
                timeout=180,
            )
            if proc.returncode == 0:
                return None
        err = (proc.stderr or b"").decode(errors="replace").strip()[-240:]
        if err:
            return f"mpv: {err}"

    return "no audio output (Docker: TaS voice needs host sound or run zani outside Docker)"


def play_bytes(data: bytes, *, audio_format: str = "pcm16") -> str | None:
    if not data or len(data) < 64:
        return "audio too short to play"
    if audio_format != "pcm16":
        handle = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            handle.write(data)
            handle.close()
            return _play_wav_file(handle.name)
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass

    last_err: str | None = None
    for rate in _PCM_RATES:
        wav = _pcm16_to_wav(data, rate)
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            handle.write(wav)
            handle.close()
            last_err = _play_wav_file(handle.name)
            if last_err is None:
                return None
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
    return last_err or "pcm16 playback failed"


def play_base64(b64: str, *, audio_format: str = "pcm16") -> str | None:
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return "invalid audio data"
    return play_bytes(raw, audio_format=audio_format)
