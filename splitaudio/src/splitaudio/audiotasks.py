"""Audio processing tasks: wav conversion, speed change, clip extraction."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from splitaudio.ffmpeg_runner import Tools, run, COMMON_PREFIX
from splitaudio.errors import SplitaudioError

log = logging.getLogger(__name__)


def make_wav(src: Path, dst: Path, tools: Tools) -> None:
    """Convert audio to 48kHz 24bit stereo WAV."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(src),
        "-map", "0:a:0",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s24le",
        str(dst),
    ]
    run(cmd)
    log.info("WAV 已生成: %s → %s", src.name, dst.name)


def make_speed(src: Path, dst: Path, tempo: float, tools: Tools) -> None:
    """Create a time-stretched MP3 at given tempo (0.8 or 1.2), preserving pitch.

    Duration tolerance: ±0.2s (LAME encoder delay + mp3 frame alignment).
    """
    if not 0.5 <= tempo <= 100.0:
        raise SplitaudioError(f"atempo 超出合法范围 [0.5, 100.0]: {tempo}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(src),
        "-map_metadata", "0",
        "-filter:a", f"atempo={tempo}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-id3v2_version", "3",
        str(dst),
    ]
    run(cmd)
    log.info("变速已生成: %s × %.1f → %s", src.name, tempo, dst.name)


def extract_clip(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    *,
    fade_in: float = 0.05,
    fade_out: float = 0.05,
    tools: Tools,
) -> None:
    """Extract a clip from src and save as MP3 with fade in/out.

    Args:
        start: Start time in seconds.
        end: End time in seconds.
        fade_in: Fade-in duration in seconds (default 50ms).
        fade_out: Fade-out duration in seconds (default 50ms).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    dur = end - start

    # Build afade filter chain
    filters = []
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        fo_start = dur - fade_out
        if fo_start < 0:
            fo_start = 0
        filters.append(f"afade=t=out:st={fo_start}:d={fade_out}")

    af = ",".join(filters) if filters else None

    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-ss", f"{start:.3f}",
        "-t", f"{dur:.3f}",
        "-i", str(src),
        "-map", "0:a:0",
    ]
    if af:
        cmd.extend(["-af", af])
    cmd.extend([
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-id3v2_version", "3",
        str(dst),
    ])

    run(cmd)
    log.info("片段已提取: %s [%.1f-%.1f] → %s", src.name, start, end, dst.name)


def copy_original(src: Path, dst: Path) -> None:
    """Bit-for-bit copy of the original file (no re-encoding)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log.info("原始文件已复制: %s → %s", src.name, dst.name)
