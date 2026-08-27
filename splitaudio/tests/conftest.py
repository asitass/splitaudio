"""pytest configuration for splitaudio tests."""

import os
from pathlib import Path

# Allow overriding test source directory via environment variable
os.environ.setdefault(
    "SPLITAUDIO_TEST_SOURCE",
    str(Path(__file__).parent.parent.parent / "test" / "source"),
)
