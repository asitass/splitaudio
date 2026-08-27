"""Cross-platform filename sanitization."""

from __future__ import annotations

import re
import unicodedata

# Characters not allowed in filenames on Windows (and some problematic on others)
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names (case-insensitive)
_WIN_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def sanitize_filename(name: str, *, max_len: int = 120) -> str:
    """Sanitize a string for use as a filename across Windows/macOS/Linux.

    Rules:
      1. Replace illegal characters and control chars with '_'
      2. Handle Windows reserved names
      3. Strip trailing dots and spaces
      4. Truncate to max_len
      5. Fallback to 'untitled' if empty
      6. Chinese characters are preserved as-is
    """
    # Normalize unicode
    name = unicodedata.normalize("NFC", name)

    # Replace illegal characters
    name = _ILLEGAL_RE.sub("_", name)

    # Strip trailing dots and spaces (Windows禁止)
    name = name.rstrip(". ")

    # Truncate
    if len(name) > max_len:
        name = name[:max_len].rstrip(". ")

    # Windows reserved names
    stem = name.split(".")[0]
    if stem.upper() in _WIN_RESERVED:
        name = f"{name}_file"

    return name if name else "untitled"
