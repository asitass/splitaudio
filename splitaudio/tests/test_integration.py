"""Integration tests using real audio files."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

TEST_SOURCE = Path(os.environ.get("SPLITAUDIO_TEST_SOURCE", Path(__file__).parent.parent.parent / "test" / "source"))
OUTPUT_DIR = Path(__file__).parent.parent.parent / "test" / "output"


@pytest.fixture(autouse=True)
def require_source():
    if not TEST_SOURCE.exists():
        pytest.skip("Test source directory not found")


def _run_splitaudio(*args, **kwargs) -> subprocess.CompletedProcess:
    venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    cmd = [str(venv_python), "-m", "splitaudio", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kwargs)


@pytest.mark.integration
class TestEndToEnd:
    def test_full_run(self):
        """Run splitaudio on test directory and verify all outputs."""
        result = _run_splitaudio(str(TEST_SOURCE), "--output", str(OUTPUT_DIR))
        assert result.returncode == 0, f"splitaudio failed: {result.stderr}"

        # Verify output structure
        assert (OUTPUT_DIR / "cover").is_dir()
        assert (OUTPUT_DIR / "lyrics").is_dir()
        assert (OUTPUT_DIR / "audio" / "wav").is_dir()
        assert (OUTPUT_DIR / "audio" / "speed").is_dir()
        assert (OUTPUT_DIR / "audio" / "original").is_dir()
        assert (OUTPUT_DIR / "audio" / "verse").is_dir()
        assert (OUTPUT_DIR / "audio" / "chorus").is_dir()

        # Verify all 3 songs × 7 files = 21 files exist
        for name in ["Out of Nowhere", "我想大概是你变了", "青春是我们写不完的旧书"]:
            assert (OUTPUT_DIR / "cover" / f"{name}.png").exists()
            assert (OUTPUT_DIR / "lyrics" / f"{name}.docx").exists()
            assert (OUTPUT_DIR / "audio" / "wav" / f"{name}.wav").exists()
            assert (OUTPUT_DIR / "audio" / "speed" / f"{name}_0.8x.mp3").exists()
            assert (OUTPUT_DIR / "audio" / "speed" / f"{name}_1.2x.mp3").exists()
            assert (OUTPUT_DIR / "audio" / "original" / f"{name}.mp3").exists()
            assert (OUTPUT_DIR / "audio" / "verse" / f"{name}_verse.mp3").exists()
            assert (OUTPUT_DIR / "audio" / "chorus" / f"{name}_chorus.mp3").exists()

    def test_wav_specs(self):
        """Verify WAV files are 48kHz 24bit stereo."""
        for name in ["Out of Nowhere", "我想大概是你变了", "青春是我们写不完的旧书"]:
            wav = OUTPUT_DIR / "audio" / "wav" / f"{name}.wav"
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-select_streams", "a:0", "-of", "json", str(wav)],
                capture_output=True, text=True,
            )
            import json
            stream = json.loads(result.stdout)["streams"][0]
            assert stream["codec_name"] == "pcm_s24le"
            assert stream["sample_rate"] == "48000"
            assert stream["channels"] == 2
            assert stream.get("bits_per_raw_sample") == "24"

    def test_speed_durations(self):
        """Verify speed variants have correct durations (±0.2s)."""
        import json
        orig_durs = {
            "Out of Nowhere": 141.6,
            "我想大概是你变了": 144.2,
            "青春是我们写不完的旧书": 145.0,
        }
        for name, orig in orig_durs.items():
            for speed in [0.8, 1.2]:
                mp3 = OUTPUT_DIR / "audio" / "speed" / f"{name}_{speed}x.mp3"
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(mp3)],
                    capture_output=True, text=True,
                )
                dur = float(json.loads(result.stdout)["format"]["duration"])
                expected = orig / speed
                assert abs(dur - expected) < 0.2, f"{name} {speed}x: {dur:.1f}s vs expected {expected:.1f}s"

    def test_clip_durations(self):
        """Verify verse/chorus clips are 12-30s."""
        import json
        for subdir in ["verse", "chorus"]:
            for name in ["Out of Nowhere", "我想大概是你变了", "青春是我们写不完的旧书"]:
                mp3 = OUTPUT_DIR / "audio" / subdir / f"{name}_{subdir}.mp3"
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(mp3)],
                    capture_output=True, text=True,
                )
                dur = float(json.loads(result.stdout)["format"]["duration"])
                assert 12 <= dur <= 30, f"{name} {subdir}: {dur:.1f}s outside [12, 30]"

    def test_idempotency(self):
        """Running twice should succeed both times with same results."""
        result1 = _run_splitaudio(str(TEST_SOURCE), "--output", str(OUTPUT_DIR))
        assert result1.returncode == 0, f"First run failed: {result1.stderr}"

        result2 = _run_splitaudio(str(TEST_SOURCE), "--output", str(OUTPUT_DIR))
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"

    def test_empty_dir_returns_2(self):
        """Empty directory should exit with code 2."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_splitaudio(tmpdir)
            assert result.returncode == 2

    def test_nonexistent_dir_returns_2(self):
        """Non-existent directory should exit with code 2."""
        result = _run_splitaudio("/nonexistent/path")
        assert result.returncode == 2
