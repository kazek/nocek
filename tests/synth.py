"""Synthetic signals with known properties, so tests need no real recordings."""

from __future__ import annotations

import numpy as np

from nocek.core.audio import Audio, Samples

SAMPLE_RATE = 384_000


def silence(duration_s: float, sample_rate: int = SAMPLE_RATE) -> Samples:
    return np.zeros(round(duration_s * sample_rate), dtype=np.float32)


def tone(
    khz: float, duration_s: float, amplitude: float = 0.5, sample_rate: int = SAMPLE_RATE
) -> Samples:
    t = np.arange(round(duration_s * sample_rate)) / sample_rate
    return (amplitude * np.sin(2 * np.pi * khz * 1000.0 * t)).astype(np.float32)


def sweep(
    start_khz: float,
    end_khz: float,
    duration_s: float,
    amplitude: float = 0.5,
    sample_rate: int = SAMPLE_RATE,
) -> Samples:
    """A linear frequency sweep, the simplest stand-in for an FM bat call."""
    t = np.arange(round(duration_s * sample_rate)) / sample_rate
    rate = (end_khz - start_khz) * 1000.0 / duration_s
    phase = 2 * np.pi * (start_khz * 1000.0 * t + rate * t**2 / 2)
    return (amplitude * np.sin(phase)).astype(np.float32)


def noise(duration_s: float, level: float = 0.002, sample_rate: int = SAMPLE_RATE) -> Samples:
    """Gaussian background, the same on every run."""
    rng = np.random.default_rng(0)
    return rng.normal(0, level, round(duration_s * sample_rate)).astype(np.float32)


def calls_at(
    call: Samples, starts_s: list[float], duration_s: float, sample_rate: int = SAMPLE_RATE
) -> Samples:
    """A call repeated at the given times over a noisy background."""
    samples = noise(duration_s, sample_rate=sample_rate)
    for start_s in starts_s:
        i = round(start_s * sample_rate)
        samples[i : i + len(call)] += call
    return samples


def sequence(
    call: Samples, n: int = 10, interval_s: float = 0.1, sample_rate: int = SAMPLE_RATE
) -> Samples:
    """A regular search sequence: n calls, one every interval."""
    starts = [i * interval_s for i in range(n)]
    return calls_at(call, starts, n * interval_s, sample_rate)


def audio(*parts: Samples, sample_rate: int = SAMPLE_RATE) -> Audio:
    return Audio(samples=np.concatenate(parts).astype(np.float32), sample_rate=sample_rate)
