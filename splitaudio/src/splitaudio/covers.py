"""Extract embedded cover art from audio files to PNG."""

from __future__ import annotations

import logging
from pathlib import Path

from splitaudio.ffmpeg_runner import Tools, run, COMMON_PREFIX

log = logging.getLogger(__name__)


def extract_cover(src: Path, dst: Path, tools: Tools) -> bool:
    """Extract the embedded cover image from an audio file to PNG.

    Returns True if a cover was extracted, False if no cover found.
    Does not create a placeholder — returns False for files without covers.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(src),
        "-map", "0:v:0",
        "-frames:v", "1",
        "-update", "1",
        str(dst),
    ]

    try:
        run(cmd)
        log.info("封面已提取: %s → %s", src.name, dst.name)
        return True
    except Exception as e:
        log.warning("无法提取封面 %s: %s", src.name, e)
        return False
