"""CLI entry point for splitaudio."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from splitaudio import __version__


def main() -> None:
    # UTF-8 reconfigure for Windows compatibility
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="splitaudio",
        description="Extract covers, lyrics, wav, speed variants, and detect chorus/verse from audio files.",
    )
    parser.add_argument("FOLDER", type=Path, help="Input folder (audio files scanned recursively)")
    parser.add_argument(
        "--task", choices=["1", "2", "all"], default="all",
        help="Which task to run (default: all)",
    )
    parser.add_argument("--output", type=Path, default=None, help="Output directory (default: FOLDER/output)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose/debug logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)-7s %(message)s",
        level=level,
        stream=sys.stderr,
    )

    folder: Path = args.FOLDER.resolve()
    output: Path = (args.output or folder / "output").resolve()

    if not folder.exists():
        logging.error("目录不存在: %s", folder)
        sys.exit(2)
    if not folder.is_dir():
        logging.error("不是目录: %s", folder)
        sys.exit(2)

    # Lazy imports to keep --help fast
    from splitaudio.ffmpeg_runner import resolve_tools
    from splitaudio.discovery import find_audio_files
    from splitaudio.tasks import run_task1, run_task2
    from splitaudio.errors import NoAudioError

    tools = resolve_tools()

    try:
        tracks = find_audio_files(folder)
    except NoAudioError as e:
        logging.error(str(e))
        sys.exit(2)

    log = logging.getLogger("splitaudio")
    log.info("找到 %d 个音频文件", len(tracks))

    task = args.task
    failures = 0

    if task in ("1", "all"):
        failures += run_task1(tracks, folder, output, tools, log)
    if task in ("2", "all"):
        failures += run_task2(tracks, folder, output, tools, log)

    if failures > 0:
        logging.warning("部分文件处理失败 (%d 个)", failures)
        sys.exit(4)

    log.info("全部完成")
