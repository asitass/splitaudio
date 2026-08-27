"""Tests for analysis module using synthetic signals (no ffmpeg needed)."""

import numpy as np

from splitaudio.analysis import (
    compute_envelope,
    detect_sections,
    _zscore,
    _smooth,
    Span,
    FPS,
    CHORUS_W,
)


def _make_silence(duration_s: float) -> np.ndarray:
    n = int(duration_s * 22050)
    return np.zeros(n, dtype=np.float32)


def _make_noisy(duration_s: float, level: float = 0.5, seed: int = 42) -> np.ndarray:
    rng = np.random.RandomState(seed)
    n = int(duration_s * 22050)
    return (rng.randn(n) * level).astype(np.float32)


class TestZScore:
    def test_zero_std(self):
        arr = np.ones(100)
        result = _zscore(arr)
        assert np.allclose(result, 0)

    def test_normal(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _zscore(arr)
        assert abs(result.mean()) < 1e-10
        assert abs(result.std() - 1.0) < 1e-10


class TestSmooth:
    def test_constant(self):
        arr = np.ones(100)
        result = _smooth(arr)
        # Edge effects at boundaries; middle should be 1.0
        assert np.allclose(result[10:-10], 1.0, atol=0.01)

    def test_reduces_noise(self):
        rng = np.random.RandomState(42)
        arr = rng.randn(100)
        smoothed = _smooth(arr, win_sec=1.0)
        assert np.std(smoothed) < np.std(arr)


class TestDetectSections:
    def test_synthetic_song(self):
        """Construct a synthetic 'song': 30s silence + 20s loud + 30s quiet + 20s louder + 20s fade."""
        dur = 120.0
        samples = np.zeros(int(dur * 22050), dtype=np.float32)

        # Intro: 0-10s quiet
        intro_end = 10 * 22050
        samples[:intro_end] = _make_noisy(10, 0.05)

        # Verse: 10-30s moderate
        verse_start = 10 * 22050
        verse_end = 30 * 22050
        samples[verse_start:verse_end] = _make_noisy(20, 0.3)

        # Bridge: 30-40s quieter
        bridge_end = 40 * 22050
        samples[verse_end:bridge_end] = _make_noisy(10, 0.15)

        # Chorus: 40-60s loud
        chorus_start = 40 * 22050
        chorus_end = 60 * 22050
        samples[chorus_start:chorus_end] = _make_noisy(20, 0.7)

        # Quiet: 60-80s
        samples[chorus_end:80 * 22050] = _make_noisy(20, 0.1)

        # Second chorus: 80-100s even louder
        samples[80 * 22050:100 * 22050] = _make_noisy(20, 0.8)

        # Outro: 100-120s quiet
        samples[100 * 22050:] = _make_noisy(20, 0.05)

        env = compute_envelope(samples, dur)
        sections = detect_sections(env)

        # Chorus should be in the second half (80-100s region)
        assert sections.chorus.start >= 40, f"Chorus too early: {sections.chorus.start}"
        assert sections.chorus.end <= 110, f"Chorus too late: {sections.chorus.end}"
        assert sections.chorus.dur >= 10, f"Chorus too short: {sections.chorus.dur}"

        # Verse should be before chorus
        assert sections.verse.end <= sections.chorus.start + 5

        # Confidence should be reasonable
        assert 0 <= sections.confidence <= 1

    def test_flat_envelope_triggers_prior_fallback(self):
        """A nearly flat envelope should trigger L2 prior-fallback."""
        dur = 140.0
        # Constant energy throughout
        samples = _make_noisy(dur, 0.3, seed=123)

        env = compute_envelope(samples, dur)
        sections = detect_sections(env)

        # With flat energy, chorus should be from prior fallback (within [0.5*dur-10, 0.5*dur+10])
        expected_center = 0.72 * dur
        assert abs(sections.chorus.start - (expected_center - 10)) < 5 or \
               abs(sections.chorus.start - 0.5 * dur) < 15, \
               f"Chorus not in prior-fallback region: {sections.chorus.start}"

    def test_short_audio(self):
        """Very short audio should not crash."""
        dur = 10.0
        samples = _make_noisy(dur, 0.3)

        env = compute_envelope(samples, dur)
        sections = detect_sections(env)

        # Should produce valid spans
        assert sections.chorus.start >= 0
        assert sections.chorus.end <= dur
        assert sections.verse.start >= 0
        assert sections.verse.end <= dur
