"""Metadata extraction from audio files (ffprobe primary, ffmetadata fallback)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from splitaudio.ffmpeg_runner import Tools, run, run_stderr, COMMON_PREFIX, FFPROBE_PREFIX
from splitaudio.errors import ProbeError

log = logging.getLogger(__name__)


@dataclass
class LyricSection:
    marker: str  # e.g. "[chorus]", "" if unmarked
    lines: list[str] = field(default_factory=list)


@dataclass
class TrackMeta:
    path: Path
    title: str
    artist: str
    duration: float
    lyrics: str
    sections: list[LyricSection] = field(default_factory=list)
    has_cover: bool = False


def probe(path: Path, tools: Tools) -> TrackMeta:
    """Extract metadata from an audio file.

    Uses ffprobe when available, falls back to ffmetadata + stderr duration.
    """
    if tools.ffprobe:
        return _probe_ffprobe(path, tools)
    return _probe_ffmetadata(path, tools)


# ---------------------------------------------------------------------------
# Primary path: ffprobe
# ---------------------------------------------------------------------------

def _probe_ffprobe(path: Path, tools: Tools) -> TrackMeta:
    cmd = [
        tools.ffprobe,
        *FFPROBE_PREFIX,
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(path),
    ]

    try:
        raw = run(cmd)
    except Exception as e:
        raise ProbeError(f"ffprobe 探测失败: {path}: {e}") from e

    data = json.loads(raw)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    tags = _extract_tags(fmt.get("tags", {}))
    duration = float(fmt.get("duration", 0))
    title = tags.get("title") or path.stem
    artist = tags.get("artist") or "未知艺术家"
    lyrics = _pick_lyrics(tags)
    has_cover = any(
        s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 1
        for s in streams
    )

    meta = TrackMeta(
        path=path,
        title=title,
        artist=artist,
        duration=duration,
        lyrics=lyrics,
        has_cover=has_cover,
    )
    meta.sections = parse_sections(lyrics)

    log.debug("ffprobe: %s — title=%s, artist=%s, dur=%.1fs, cover=%s",
              path.name, title, artist, duration, has_cover)
    return meta


def _extract_tags(raw_tags: Mapping[str, str | list[str]]) -> dict[str, str]:
    """Flatten tags that might be strings or lists into a flat dict."""
    result: dict[str, str] = {}
    for k, v in raw_tags.items():
        result[k.lower().replace(" ", "-")] = v if isinstance(v, str) else v[0] if v else ""
    return result


# ---------------------------------------------------------------------------
# Fallback path: ffmetadata + stderr duration (no ffprobe)
# ---------------------------------------------------------------------------

def _probe_ffmetadata(path: Path, tools: Tools) -> TrackMeta:
    log.info("ffprobe 不可用，使用 ffmetadata 降级: %s", path.name)

    # Get tags via ffmetadata
    tags = _ffmetadata_tags(path, tools)

    # Get duration via stderr
    duration = _duration_from_stderr(path, tools)

    title = tags.get("title") or path.stem
    artist = tags.get("artist") or "未知艺术家"
    lyrics = _pick_lyrics(tags)

    # Cover detection: try to extract a video frame; if it succeeds, there's a cover
    has_cover = _has_cover_probe(path, tools)

    meta = TrackMeta(
        path=path,
        title=title,
        artist=artist,
        duration=duration,
        lyrics=lyrics,
        has_cover=has_cover,
    )
    meta.sections = parse_sections(lyrics)
    return meta


def _ffmetadata_tags(path: Path, tools: Tools) -> dict[str, str]:
    """Extract tags using `ffmpeg -f ffmetadata`."""
    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(path),
        "-f", "ffmetadata",
        "pipe:1",
    ]

    try:
        raw = run(cmd).decode("utf-8", errors="replace")
    except Exception:
        return {}

    tags: dict[str, str] = {}
    pending_key: str | None = None
    pending_lines: list[str] = []

    for line in raw.split("\n"):
        # ffmetadata uses line-ending \ for continuation
        if pending_key is not None:
            if line.endswith("\\"):
                pending_lines.append(line[:-1])
                continue
            else:
                pending_lines.append(line)
                tags[pending_key] = "\n".join(pending_lines)
                pending_key = None
                pending_lines = []
                continue

        if "=" in line:
            k, v = line.split("=", 1)
            # Handle escaped semicolons and backslashes
            v = v.replace("\\;", ";").replace("\\\\", "\\")
            if v.endswith("\\"):
                pending_key = k.lower().replace(" ", "-")
                pending_lines = [v[:-1]]
            else:
                tags[k.lower().replace(" ", "-")] = v

    # Flush pending
    if pending_key is not None:
        tags[pending_key] = "\n".join(pending_lines)

    return tags


def _duration_from_stderr(path: Path, tools: Tools) -> float:
    """Extract duration by parsing ffmpeg stderr output."""
    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(path),
        "-f", "null",
        "-",
    ]
    try:
        stderr = run_stderr(cmd).decode("utf-8", errors="replace")
    except Exception:
        return 0.0

    # Match "Duration: 00:02:24.19"
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if m:
        h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return h * 3600 + mi * 60 + s
    return 0.0


def _has_cover_probe(path: Path, tools: Tools) -> bool:
    """Probe if file has a cover image by trying to extract one."""
    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(path),
        "-map", "0:v",
        "-frames:v", "1",
        "-f", "null",
        "-",
    ]
    try:
        run(cmd)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lyrics extraction and section parsing
# ---------------------------------------------------------------------------

_LYRICS_KEYS = {"lyrics-eng", "lyrics", "unsynclyrics", "lyric"}


def _pick_lyrics(tags: Mapping[str, str]) -> str:
    """Pick the best lyrics value from tags, normalizing key variants."""
    for key, val in tags.items():
        normalized = key.lower().replace("_", "-")
        if normalized in _LYRICS_KEYS:
            return val
    return ""


def parse_sections(lyrics: str) -> list[LyricSection]:
    """Parse lyrics text into sections based on bracket markers.

    E.g. '[Verse 1]\\nLine 1\\nLine 2\\n[Chorus]\\nLine 3'
    → [LyricSection(marker='[Verse 1]', lines=['Line 1', 'Line 2']),
       LyricSection(marker='[Chorus]', lines=['Line 3'])]
    """
    if not lyrics.strip():
        return [LyricSection(marker="", lines=lyrics.split("\n") if lyrics else [])]

    section_re = re.compile(r"^\[(.+?)\]\s*$", re.MULTILINE | re.IGNORECASE)
    sections: list[LyricSection] = []

    last_end = 0
    for m in section_re.finditer(lyrics):
        if m.start() > last_end:
            intro_text = lyrics[last_end:m.start()].strip()
            if intro_text:
                sections.append(LyricSection(marker="", lines=intro_text.split("\n")))
        last_end = m.end()

    # Remaining text after last marker
    remaining = lyrics[last_end:].strip()
    if remaining:
        # Check if last match was the end
        if not sections or sections[-1].marker:
            sections.append(LyricSection(marker="", lines=[]))

    # Rebuild properly: split by markers
    parts = section_re.split(lyrics)
    # parts = [text_before, marker, text_after, marker, ...]
    result: list[LyricSection] = []
    i = 0
    # Skip leading text before first marker (if any)
    if parts[0].strip():
        # This is intro text before any marker
        pass

    i = 1
    while i < len(parts) - 1:
        marker = f"[{parts[i]}]"
        body = parts[i + 1]
        lines = [l for l in body.split("\n") if l.strip() or not body.strip()]
        result.append(LyricSection(marker=marker, lines=lines))
        i += 2

    # Handle text before first marker
    if parts[0].strip() and result:
        intro = LyricSection(marker="", lines=parts[0].strip().split("\n"))
        result.insert(0, intro)
    elif parts[0].strip():
        result.append(LyricSection(marker="", lines=parts[0].strip().split("\n")))

    return result if result else [LyricSection(marker="", lines=[""])]
