"""ffmpeg/ffprobe tool resolution and subprocess wrapper."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

from splitaudio.errors import FFmpegNotFoundError

log = logging.getLogger(__name__)

COMMON_PREFIX = ["-y", "-nostdin", "-hide_banner", "-loglevel", "error"]


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str | None


def resolve_tools() -> Tools:
    """Resolve ffmpeg and ffprobe paths.

    Resolution order for ffmpeg:
      SPLITAUDIO_FFMPEG env -> shutil.which("ffmpeg") -> imageio_ffmpeg fallback

    Resolution order for ffprobe:
      SPLITAUDIO_FFPROBE env -> shutil.which("ffprobe") -> None (degraded mode)
    """
    ffmpeg = _resolve_ffmpeg()
    ffprobe = _resolve_ffprobe()
    return Tools(ffmpeg=ffmpeg, ffprobe=ffprobe)


def _resolve_ffmpeg() -> str:
    env = os.environ.get("SPLITAUDIO_FFMPEG")
    if env:
        return env

    which = shutil.which("ffmpeg")
    if which:
        return which

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    raise FFmpegNotFoundError()


def _resolve_ffprobe() -> str | None:
    env = os.environ.get("SPLITAUDIO_FFPROBE")
    if env:
        return env

    which = shutil.which("ffprobe")
    if which:
        return which

    return None


def run(cmd: list[str], *, timeout: int = 300) -> bytes:
    """Run a command with capture_output, raise on failure.

    The exception message includes the last 500 bytes of stderr for debugging.
    """
    log.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        check=True,
    )
    return result.stdout


def run_stderr(cmd: list[str], *, timeout: int = 300) -> bytes:
    """Run a command and return stderr (for duration extraction, etc.)."""
    log.debug("Running (stderr capture): %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        check=True,
    )
    return result.stderr
