"""Exception hierarchy for splitaudio."""


class SplitaudioError(Exception):
    """Base exception for splitaudio."""


class FFmpegNotFoundError(SplitaudioError):
    """ffmpeg binary not found on the system."""

    def __init__(self) -> None:
        msg = (
            "ffmpeg not found. Install it:\n"
            "  Linux:  sudo apt install ffmpeg\n"
            "  macOS:  brew install ffmpeg\n"
            "  Windows: winget install ffmpeg\n"
            "Or: pip install splitaudio[fallback] (bundles ffmpeg binary)\n"
            "Or set SPLITAUDIO_FFMPEG env var to full path."
        )
        super().__init__(msg)


class NoAudioError(SplitaudioError):
    """No audio files found in the input directory."""


class ProbeError(SplitaudioError):
    """Metadata probing failed for an audio file."""
