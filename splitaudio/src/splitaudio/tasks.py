"""Task orchestration: run_task1 and run_task2."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from splitaudio.ffmpeg_runner import Tools
from splitaudio.metadata import TrackMeta, probe
from splitaudio.naming import sanitize_filename
from splitaudio.covers import extract_cover
from splitaudio.audiotasks import make_wav, make_speed, copy_original
from splitaudio.lyrics_docx import write_lyrics_docx

log = logging.getLogger(__name__)


def run_task1(
    tracks: list[Path],
    source_dir: Path,
    output_dir: Path,
    tools: Tools,
    logger: logging.Logger,
) -> int:
    """Run Task 1: cover PNG + wav 48k24bit + 0.8x/1.2x mp3 + lyrics docx.

    Returns number of failures (0 = all success).
    """
    cover_dir = output_dir / "cover"
    wav_dir = output_dir / "audio" / "wav"
    speed_dir = output_dir / "audio" / "speed"
    lyrics_dir = output_dir / "lyrics"

    failures = 0
    for path in tracks:
        try:
            meta = probe(path, tools)
            safe_name = sanitize_filename(meta.title)

            # Cover
            if meta.has_cover:
                extract_cover(path, cover_dir / f"{safe_name}.png", tools)
            else:
                logger.warning("跳过封面: %s (无内嵌封面)", meta.title)

            # WAV 48kHz 24bit
            make_wav(path, wav_dir / f"{safe_name}.wav", tools)

            # Speed variants
            make_speed(path, speed_dir / f"{safe_name}_0.8x.mp3", 0.8, tools)
            make_speed(path, speed_dir / f"{safe_name}_1.2x.mp3", 1.2, tools)

            # Lyrics docx
            write_lyrics_docx(meta, lyrics_dir / f"{safe_name}.docx")

            logger.info("✓ Task 1 完成: %s", meta.title)
        except Exception as e:
            logger.error("✗ Task 1 失败: %s — %s", path.name, e)
            failures += 1

    return failures


def run_task2(
    tracks: list[Path],
    source_dir: Path,
    output_dir: Path,
    tools: Tools,
    logger: logging.Logger,
) -> int:
    """Run Task 2: original mp3 + verse clip + chorus clip + lyrics docx.

    Returns number of failures (0 = all success).
    """
    from splitaudio.analysis import decode_envelope, detect_sections
    from splitaudio.audiotasks import extract_clip

    original_dir = output_dir / "audio" / "original"
    verse_dir = output_dir / "audio" / "verse"
    chorus_dir = output_dir / "audio" / "chorus"
    lyrics_dir = output_dir / "lyrics"

    failures = 0
    for path in tracks:
        try:
            meta = probe(path, tools)
            safe_name = sanitize_filename(meta.title)

            # Original (bit-for-bit copy)
            copy_original(path, original_dir / f"{safe_name}.mp3")

            # Detect sections
            env = decode_envelope(path, tools)
            sections = detect_sections(env)

            logger.info("检测结果: %s — verse [%.1f, %.1f] chorus [%.1f, %.1f] (conf=%.2f, method=%s)",
                        meta.title,
                        sections.verse.start, sections.verse.end,
                        sections.chorus.start, sections.chorus.end,
                        sections.confidence, sections.method)

            # Determine fade parameters based on alignment
            vi_fi, vi_fo = 0.05, 0.05  # aligned → short fades
            co_fi, co_fo = 0.05, 0.05

            # Verse clip
            extract_clip(
                path,
                verse_dir / f"{safe_name}_verse.mp3",
                sections.verse.start,
                sections.verse.end,
                fade_in=vi_fi,
                fade_out=vi_fo,
                tools=tools,
            )

            # Chorus clip
            extract_clip(
                path,
                chorus_dir / f"{safe_name}_chorus.mp3",
                sections.chorus.start,
                sections.chorus.end,
                fade_in=co_fi,
                fade_out=co_fo,
                tools=tools,
            )

            # Lyrics docx (shared with task1)
            write_lyrics_docx(meta, lyrics_dir / f"{safe_name}.docx")

            logger.info("✓ Task 2 完成: %s", meta.title)
        except Exception as e:
            logger.error("✗ Task 2 失败: %s — %s", path.name, e)
            failures += 1

    return failures
