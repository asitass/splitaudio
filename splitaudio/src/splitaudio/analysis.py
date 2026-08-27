"""Core analysis: 4-feature chorus/verse detection via signal processing.

Implements the full algorithm from the implementation plan §5:
- PCM decode → STFT → 4 envelopes (RMS, centroid, vocal, repetition)
- Sliding window scoring with position prior
- Boundary refinement (valley alignment)
- Degradation chain L0-L3
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.fft import rfft, rfftfreq

from splitaudio.ffmpeg_runner import Tools, COMMON_PREFIX

log = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

SR = 22050          # Sample rate for analysis
HOP_MS = 100        # Hop size in ms → 10 fps
HOP = int(SR * HOP_MS / 1000)
FRAME_LEN = 8820    # 400ms frames
WINDOW = np.hanning(FRAME_LEN)
FPS = SR / HOP      # frames per second

CHORUS_W = 200      # 20s sliding window (200 frames at 10fps)
MIN_CHORUS_DUR = 15.0
MAX_CHORUS_DUR = 25.0
MIN_VERSE_DUR = 12.0
MAX_VERSE_DUR = 25.0


@dataclass
class Span:
    start: float
    end: float

    @property
    def dur(self) -> float:
        return self.end - self.start


@dataclass
class Sections:
    verse: Span
    chorus: Span
    confidence: float
    method: str  # "features" | "energy+brightness" | "prior-fallback"


@dataclass
class Envelope:
    rms: np.ndarray       # Normalized RMS (10fps)
    cent: np.ndarray      # Spectral centroid in kHz (10fps)
    voc: np.ndarray       # Vocal band ratio (10fps)
    rep: np.ndarray       # Repetition score (10fps)
    duration: float       # Duration in seconds
    n_frames: int         # Number of frames


# ─── Decode PCM ───────────────────────────────────────────────────────────────

def decode_pcm(path: Path, tools: Tools) -> tuple[np.ndarray, float]:
    """Decode audio to mono PCM at 22050Hz via ffmpeg pipe.

    Returns (samples as float32 in [-1,1], duration_seconds).
    """
    cmd = [
        tools.ffmpeg,
        *COMMON_PREFIX,
        "-i", str(path),
        "-vn",
        "-ac", "1",
        "-ar", str(SR),
        "-f", "s16le",
        "pipe:1",
    ]

    log.debug("PCM 解码: %s", path.name)
    result = subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    pcm_bytes = result.stdout

    if len(pcm_bytes) == 0:
        raise RuntimeError(f"PCM 解码返回空数据: {path.name}")

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    duration = len(samples) / SR
    log.debug("PCM: %d samples, %.1fs", len(samples), duration)
    return samples, duration


# ─── STFT ─────────────────────────────────────────────────────────────────────

def _stft(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute STFT magnitude spectrum.

    Returns:
        spec: (n_frames, freq_bins) magnitude
        freqs: (freq_bins,) frequency axis in Hz
    """
    n_frames = (len(samples) - FRAME_LEN) // HOP + 1
    spec = np.zeros((n_frames, FRAME_LEN // 2 + 1), dtype=np.float32)

    for i in range(n_frames):
        start = i * HOP
        frame = samples[start:start + FRAME_LEN] * WINDOW
        spec[i] = np.abs(rfft(frame))

    freqs = rfftfreq(FRAME_LEN, d=1.0 / SR)
    return spec, freqs


# ─── Feature Extraction ──────────────────────────────────────────────────────

def _compute_rms(spec: np.ndarray) -> np.ndarray:
    """RMS energy per frame, normalized by p95."""
    rms = np.sqrt(np.mean(spec ** 2, axis=1))
    p95 = np.percentile(rms, 95)
    if p95 > 0:
        rms = rms / p95
    return rms


def _compute_centroid(spec: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Spectral centroid in kHz."""
    eps = 1e-10
    freq_grid = np.broadcast_to(freqs, spec.shape)
    cent = np.sum(spec * freq_grid, axis=1) / (np.sum(spec, axis=1) + eps)
    return cent / 1000.0  # to kHz


def _compute_vocal(spec: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Vocal band ratio: energy in 200Hz–4kHz / total energy."""
    eps = 1e-10
    vocal_mask = (freqs >= 200) & (freqs <= 4000)
    total = np.sum(spec, axis=1)
    vocal = np.sum(spec[:, vocal_mask], axis=1)
    return vocal / (total + eps)


def _compute_repetition(spec: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Repetition score using chroma + context + Pearson correlation.

    1. Fold spectrum into 12 pitch classes (chroma)
    2. Context concatenation: ±0.5s (±5 frames) → 132-dim vectors
    3. Pearson correlation SSM
    4. Exclude ±10s neighborhood
    5. rep[i] = max similarity (excluding self and neighbors)
    """
    n_frames = spec.shape[0]

    # 1. Chroma: fold >55Hz bins into 12 pitch classes
    midi = 69 + 12 * np.log2(np.maximum(freqs, 1.0) / 440.0)
    pc = np.mod(midi.astype(int), 12)
    ch = np.zeros((n_frames, 12), dtype=np.float32)
    for i, f in enumerate(freqs):
        if f < 55:
            continue
        ch[:, pc[i]] += spec[:, i]

    # 2. Context concatenation: ±5 frames → 132-dim
    ctx = 5
    padded = np.pad(ch, ((ctx, ctx), (0, 0)), mode="edge")
    ctxv = np.concatenate([padded[i:i + 2 * ctx + 1].ravel()
                           for i in range(n_frames)], axis=0)
    ctxv = ctxv.reshape(n_frames, -1)

    # 3. Pearson correlation (row-normalized)
    row_mean = ctxv.mean(axis=1, keepdims=True)
    m = ctxv - row_mean
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    mn = m / norms
    sim = mn @ mn.T  # (n_frames, n_frames)

    # 4. Exclude ±10s neighborhood (±100 frames at 10fps)
    exclude = 100
    for i in range(n_frames):
        lo = max(0, i - exclude)
        hi = min(n_frames, i + exclude + 1)
        sim[i, lo:hi] = -2.0

    # 5. rep[i] = max similarity
    rep = sim.max(axis=1)

    return rep


def _smooth(arr: np.ndarray, win_sec: float = 1.0) -> np.ndarray:
    """1D rectangular moving average smoothing."""
    win = max(1, int(FPS * win_sec))
    kernel = np.ones(win) / win
    return np.convolve(arr, kernel, mode="same")


def _zscore(arr: np.ndarray) -> np.ndarray:
    """Z-score normalization."""
    std = arr.std()
    if std < 1e-10:
        return np.zeros_like(arr)
    return (arr - arr.mean()) / std


def compute_envelope(samples: np.ndarray, duration: float) -> Envelope:
    """Compute all 4 feature envelopes from PCM samples."""
    spec, freqs = _stft(samples)
    n_frames = spec.shape[0]

    rms_raw = _compute_rms(spec)
    cent_raw = _compute_centroid(spec, freqs)
    voc_raw = _compute_vocal(spec, freqs)

    # Check for repetition viability
    rep_ok = True
    try:
        rep_raw = _compute_repetition(spec, freqs)
        if np.std(rep_raw) < 0.02:
            rep_ok = False
            log.warning("重复度特征 std=%.3f < 0.02，降级为 L1", np.std(rep_raw))
    except Exception as e:
        rep_ok = False
        log.warning("重复度计算异常: %s，降级为 L1", e)

    # Smooth
    rms = _smooth(rms_raw)
    cent = _smooth(cent_raw)
    voc = _smooth(voc_raw)

    if rep_ok:
        rep = _smooth(rep_raw)
    else:
        rep = np.zeros(n_frames)

    return Envelope(
        rms=rms,
        cent=cent,
        voc=voc,
        rep=rep,
        duration=duration,
        n_frames=n_frames,
    )


# ─── Decode + Envelope (high-level) ──────────────────────────────────────────

def decode_envelope(path: Path, tools: Tools) -> Envelope:
    """Full pipeline: decode audio → compute 4-feature envelope."""
    samples, duration = decode_pcm(path, tools)
    return compute_envelope(samples, duration)


# ─── Chorus Detection ────────────────────────────────────────────────────────

def _position_prior(center_idx: int, n_frames: int) -> float:
    """Position prior: boost score based on where the center falls in the song."""
    pos = center_idx / max(n_frames, 1)
    if 0.50 <= pos <= 0.85:
        return 1.0   # Sweet spot for chorus
    elif pos < 0.50:
        return 0.5   # Earlier — possible first chorus
    else:
        return 0.2   # Late — penalize outro


def _find_valley(arr: np.ndarray, center: int, search_range: int = 40) -> int:
    """Find nearest energy valley within ±search_range frames of center.

    A valley is where arr[j] <= arr[j±3] and arr[j] < 0.75 * mean(arr around center).
    Returns center if no valley found.
    """
    lo = max(0, center - search_range)
    hi = min(len(arr), center + search_range + 1)
    window_mean = arr[lo:hi].mean() if hi > lo else arr[center]
    threshold = 0.75 * window_mean

    best = center
    best_val = arr[center]

    for j in range(lo, hi):
        if arr[j] < threshold:
            # Check if local minimum: <= neighbors ±3
            left = arr[max(0, j - 3)] if j >= 3 else arr[j]
            right = arr[min(len(arr) - 1, j + 3)] if j + 3 < len(arr) else arr[j]
            if arr[j] <= left and arr[j] <= right and arr[j] < best_val:
                best = j
                best_val = arr[j]

    return best


def _refine_chorus_boundaries(
    rms: np.ndarray,
    start: int,
    end: int,
    n_frames: int,
) -> tuple[int, int, bool, bool]:
    """Refine chorus boundaries by finding energy valleys.

    Returns (new_start, new_end, start_aligned, end_aligned).
    """
    # Left boundary: search ±4s (40 frames) outward
    left = _find_valley(rms, start, search_range=40)
    start_aligned = (left != start)

    # Right boundary: search ±4s outward
    right = _find_valley(rms, end, search_range=40)
    end_aligned = (right != end)

    # Clamp length to [15s, 25s] in frames
    min_frames = int(MIN_CHORUS_DUR * FPS)
    max_frames = int(MAX_CHORUS_DUR * FPS)
    dur = right - left

    if dur < min_frames:
        # Expand symmetrically
        pad = (min_frames - dur) // 2
        left = max(0, left - pad)
        right = min(n_frames, right + pad)
    elif dur > max_frames:
        # Shrink, keeping energy centroid centered
        mid = (left + right) // 2
        half = max_frames // 2
        left = max(0, mid - half)
        right = min(n_frames, mid + half)

    return left, right, start_aligned, end_aligned


def detect_chorus(env: Envelope) -> tuple[Span, bool, bool]:
    """Detect chorus using 3-feature sliding window + position prior.

    Returns (chorus_span, start_aligned, end_aligned).
    """
    n = env.n_frames

    if n < CHORUS_W:
        # Too short — use full range
        return Span(0, env.duration), False, False

    # Check for L2 degradation trigger: energy flat (p95/p50 < 1.15)
    p95 = np.percentile(env.rms, 95)
    p50 = np.median(env.rms)
    if p95 / max(p50, 1e-10) < 1.15:
        log.warning("能量平坦 (p95/p50=%.2f)，触发 L2 降级", p95 / max(p50, 1e-10))
        return _prior_fallback_chorus(env)

    # Z-score normalization
    z_rms = _zscore(env.rms)
    z_cent = _zscore(env.cent)
    z_rep = _zscore(env.rep)

    # Sliding window scoring
    best_score = -np.inf
    best_idx = 0
    search_start = int(0.15 * n)
    search_end = int(0.90 * n)

    for i in range(search_start, max(search_end - CHORUS_W, search_start + 1)):
        window = slice(i, i + CHORUS_W)
        score = (
            z_rms[window].mean()
            + z_cent[window].mean()
            + z_rep[window].mean()
            + _position_prior(i + CHORUS_W // 2, n)
        )
        if score > best_score:
            best_score = score
            best_idx = i

    # Refine boundaries
    new_start, new_end, sa, ea = _refine_chorus_boundaries(
        env.rms, best_idx, best_idx + CHORUS_W, n
    )

    # Convert to seconds
    start_s = new_start / FPS
    end_s = new_end / FPS
    log.debug("副歌检测: [%.1f, %.1f] (raw [%.1f, %.1f]), aligned=%s/%s",
              start_s, end_s, best_idx / FPS, (best_idx + CHORUS_W) / FPS, sa, ea)

    return Span(start_s, end_s), sa, ea


def _prior_fallback_chorus(env: Envelope) -> tuple[Span, bool, bool]:
    """L2 fallback: use Suno structure prior."""
    dur = env.duration
    center = 0.72 * dur
    start = max(0, center - 10)
    end = min(dur, center + 10)
    log.warning("L2 降级: 使用结构先验 [%.1f, %.1f]", start, end)
    return Span(start, end), False, False


# ─── Verse Detection ─────────────────────────────────────────────────────────

def _detect_intro_end(env: Envelope) -> int:
    """Find where the intro ends.

    Uses a combined approach:
    1. First, try to find where energy first sustains above a moderate baseline
    2. Clamp to reasonable range [5s, 15s] for typical pop songs
    """
    # Moderate baseline: 30% of p95
    p95 = np.percentile(env.rms, 95)
    threshold = 0.3 * p95
    if threshold < 0.15:
        threshold = 0.15

    sustain = int(1.5 * FPS)  # 1.5 seconds

    count = 0
    for i in range(len(env.rms)):
        if env.rms[i] > threshold:
            count += 1
            if count >= sustain:
                result = i - sustain + 1
                # Clamp to [5s, 15s]
                min_f = int(5 * FPS)
                max_f = int(15 * FPS)
                return max(min_f, min(max_f, result))
        else:
            count = 0

    return int(8 * FPS)  # Default 8s


def _detect_first_energy_jump(env: Envelope, intro_end: int, chorus_start: int) -> int:
    """Find where the verse ends (the energy jumps to chorus-like levels).

    Simple approach: find the last low-energy point before the chorus starts.
    This gives us the end of the verse section.
    """
    # Look in the region before the chorus
    search_start = max(intro_end, int(0.15 * env.n_frames))
    search_end = min(chorus_start, len(env.rms))

    if search_end <= search_start:
        return min(intro_end + int(20 * FPS), len(env.rms) - 1)

    # Find the last point where energy is below chorus average
    chorus_avg = env.rms[max(0, chorus_start - 20):chorus_start + 20].mean()
    threshold = 0.7 * chorus_avg

    last_below = search_start
    for t in range(search_start, search_end):
        if env.rms[t] < threshold:
            last_below = t

    # Add a small buffer (2s) after the last below-threshold point
    result = min(last_below + int(2 * FPS), search_end)

    # Ensure minimum verse duration
    min_verse = int(MIN_VERSE_DUR * FPS)
    if result - intro_end < min_verse:
        result = min(intro_end + min_verse, search_end)

    return result


def detect_verse(env: Envelope, chorus: Span) -> Span:
    """Detect verse: between intro end and first energy jump."""
    n = env.n_frames
    chorus_start_frame = int(chorus.start * FPS)

    intro_end = _detect_intro_end(env)
    first_jump = _detect_first_energy_jump(env, intro_end, chorus_start_frame)

    # Verse from intro_end to first_jump (clamped to max verse duration)
    verse_start = intro_end / FPS
    verse_end_frames = min(first_jump, int(verse_start * FPS) + int(MAX_VERSE_DUR * FPS))
    verse_end = verse_end_frames / FPS

    # Ensure minimum duration
    if verse_end - verse_start < MIN_VERSE_DUR / FPS:
        # Expand backward toward intro
        verse_start = max(0, verse_end - MIN_VERSE_DUR / FPS)

    # Clamp
    verse_start = max(0, verse_start)
    verse_end = min(env.duration, verse_end)

    if verse_end <= verse_start:
        # Fallback: verse before chorus
        verse_start = max(0, chorus.start - 25)
        verse_end = chorus.start - 1

    log.debug("主歌检测: [%.1f, %.1f] (intro_end=%.1fs, first_jump=%.1fs)",
              verse_start, verse_end, intro_end / FPS, first_jump / FPS)
    return Span(verse_start, verse_end)


# ─── Confidence ──────────────────────────────────────────────────────────────

def _compute_confidence(env: Envelope, chorus: Span) -> float:
    """Confidence based on how much louder the chorus is vs median."""
    cs = int(chorus.start * FPS)
    ce = int(chorus.end * FPS)
    chorus_rms = env.rms[cs:ce].mean() if ce > cs else env.rms.mean()
    p50 = np.median(env.rms)
    ratio = chorus_rms / max(p50, 1e-10)
    conf = min(max((ratio - 1) / 1.0, 0), 1)
    return conf


# ─── Main Entry Point ────────────────────────────────────────────────────────

def detect_sections(env: Envelope) -> Sections:
    """Detect verse and chorus sections from 4-feature envelope.

    Degradation chain:
      L0: full features (energy+brightness+repetition)
      L1: energy+brightness (repetition abnormal)
      L2: prior-fallback (energy flat)
      L3: per-file error (handled in caller)
    """
    method = "features"

    # Detect chorus
    chorus, sa, ea = detect_chorus(env)

    # Detect verse
    verse = detect_verse(env, chorus)

    # Clamp both to valid ranges
    chorus = Span(
        max(0, chorus.start),
        min(env.duration, chorus.end),
    )
    verse = Span(
        max(0, verse.start),
        min(env.duration, verse.end),
    )

    # Confidence
    confidence = _compute_confidence(env, chorus)

    # Determine method name
    p95 = np.percentile(env.rms, 95)
    p50 = np.median(env.rms)
    if env.rep.std() < 0.02:
        method = "energy+brightness"
    elif p95 / max(p50, 1e-10) < 1.15:
        method = "prior-fallback"
        confidence = 0.3

    # Direction consistency check (log)
    cs = int(chorus.start * FPS)
    ce = int(chorus.end * FPS)
    if ce > cs:
        z_rms_c = _zscore(env.rms)[cs:ce].mean()
        z_cent_c = _zscore(env.cent)[cs:ce].mean()
        z_rep_c = _zscore(env.rep)[cs:ce].mean()
        log.debug("副歌区 z-score: rms=%.2f cent=%.2f rep=%.2f",
                  z_rms_c, z_cent_c, z_rep_c)

    return Sections(
        verse=verse,
        chorus=chorus,
        confidence=confidence,
        method=method,
    )
