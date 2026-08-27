# splitaudio

Extract covers, lyrics, audio variants, and detect chorus/verse sections from audio files.

## Requirements

- **Python 3.10+**
- **ffmpeg** (must be in PATH)

### Installing ffmpeg

```bash
# Linux (Ubuntu/Debian)
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install ffmpeg
```

Or install the bundled fallback:

```bash
pip install ".[fallback]"
```

## Installation

```bash
cd splitaudio
pip install -e .
```

## Usage

```bash
# Run both tasks (cover + wav + speed + lyrics + verse/chorus clips)
splitaudio /path/to/test

# Run only Task 1 (cover, wav, speed, lyrics)
splitaudio --task 1 /path/to/test

# Run only Task 2 (original, verse, chorus clips)
splitaudio --task 2 /path/to/test

# Custom output directory
splitaudio --output /path/to/output /path/to/test

# Verbose logging
splitaudio -v /path/to/test
```

Or run as a module:

```bash
python -m splitaudio /path/to/test
```

## Output Structure

```
output/
├── cover/                     # Task 1: Cover images (PNG)
│   ├── Song1.png
│   └── Song2.png
├── lyrics/                    # Task 1+2: Lyrics (DOCX)
│   ├── Song1.docx
│   └── Song2.docx
└── audio/
    ├── wav/                   # Task 1: 48kHz 24bit WAV
    │   └── Song1.wav
    ├── speed/                 # Task 1: Speed variants
    │   ├── Song1_0.8x.mp3
    │   └── Song1_1.2x.mp3
    ├── original/              # Task 2: Original MP3 (bit-for-bit copy)
    │   └── Song1.mp3
    ├── verse/                 # Task 2: Verse clips
    │   └── Song1_verse.mp3
    └── chorus/                # Task 2: Chorus highlight clips
        └── Song1_chorus.mp3
```

## How It Works

1. **Metadata extraction**: Reads title, artist, lyrics, and cover art from ID3 tags (no external data sources)
2. **Cover extraction**: Extracts embedded JPEG covers and converts to PNG
3. **Audio conversion**: Converts to 48kHz 24bit WAV and creates 0.8x/1.2x speed variants using ffmpeg's atempo filter
4. **Chorus/verse detection**: Uses 4-feature signal analysis (RMS energy, spectral centroid, vocal band ratio, chroma repetition) with sliding window scoring and position priors
5. **Lyrics DOCX**: Generates formatted Word documents with Chinese font support

## Algorithm

The chorus detection uses a multi-feature voting approach:
- **RMS Energy**: Louder sections tend to be choruses
- **Spectral Centroid**: Choruses are typically "brighter"
- **Vocal Band Ratio**: Identifies vocal presence
- **Chroma Repetition**: Choruses are the most repeated sections (strongest single feature)

A sliding window scores combinations of these features with position priors (choruses typically occur in the 50-85% range of a song).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Usage/input error (directory doesn't exist, no audio files) |
| 3 | ffmpeg not found |
| 4 | Some files failed to process |

## Testing

```bash
# Unit tests (fast, no ffmpeg needed)
pytest tests/test_naming.py tests/test_lyrics.py tests/test_analysis.py

# Integration tests (requires ffmpeg + test audio files)
pytest tests/test_integration.py -m integration

# All tests
pytest tests/
```

## Project Structure

```
splitaudio/
├── pyproject.toml
├── README.md
├── docs/
│   ├── implementation-plan.md
│   └── completion-report.md
├── src/splitaudio/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # CLI entry point
│   ├── errors.py           # Exception hierarchy
│   ├── ffmpeg_runner.py    # Tool resolution + subprocess
│   ├── naming.py           # Filename sanitization
│   ├── discovery.py        # Recursive audio file scanner
│   ├── metadata.py         # Metadata extraction (ffprobe/ffmetadata)
│   ├── analysis.py         # Core chorus/verse detection algorithm
│   ├── covers.py           # Cover art extraction
│   ├── audiotasks.py       # WAV/speed/clip processing
│   ├── lyrics_docx.py      # DOCX lyrics generation
│   └── tasks.py            # Task orchestration
└── tests/
    ├── conftest.py
    ├── test_naming.py
    ├── test_lyrics.py
    ├── test_analysis.py
    └── test_integration.py
```

## License

Internal use only.
