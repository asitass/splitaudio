"""Recursive discovery of audio files."""

from __future__ import annotations

import logging
from pathlib import Path

from splitaudio.errors import NoAudioError

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".wma", ".opus"}

log = logging.getLogger(__name__)


def find_audio_files(root: Path) -> list[Path]:
    """Recursively scan root for audio files, returning a sorted list.

    Raises NoAudioError if no audio files are found.
    """
    if not root.exists():
        raise NoAudioError(f"目录不存在: {root}")
    if not root.is_dir():
        raise NoAudioError(f"不是目录: {root}")

    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )

    if not files:
        raise NoAudioError(f"在 {root} 中未找到音频文件")

    log.info("发现 %d 个音频文件", len(files))
    for f in files:
        log.debug("  %s", f)

    return files
