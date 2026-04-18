"""Metrics for schedule quality and grid friendliness."""

from __future__ import annotations

import numpy as np


def weighted_overlap(load: np.ndarray, stress: np.ndarray) -> float:
    """Compute load-stress overlap (higher means less grid-friendly)."""
    return float(np.sum(load * stress))


def peak_load(load: np.ndarray) -> float:
    return float(np.max(load))


def grid_friendliness_score(load: np.ndarray, stress: np.ndarray) -> float:
    """
    Convert overlap into an intuitive 0-100 score.

    100 is best (minimal overlap with stressed hours), 0 is worst.
    """
    overlap = weighted_overlap(load, stress)
    denom = float((np.max(load) + 1e-9) * (np.max(stress) + 1e-9) * len(load))
    ratio = overlap / (denom + 1e-9)
    score = 100.0 * (1.0 - ratio)
    return float(np.clip(score, 0.0, 100.0))


def peak_overlap_reduction(before_load: np.ndarray, after_load: np.ndarray, stress: np.ndarray) -> float:
    """Percent reduction in weighted overlap between baseline and optimized profile."""
    before = weighted_overlap(before_load, stress)
    after = weighted_overlap(after_load, stress)
    if before <= 1e-9:
        return 0.0
    return float(((before - after) / before) * 100.0)


def load_variance_reduction(before_load: np.ndarray, after_load: np.ndarray) -> float:
    """Percent reduction in load variance (smoother profile is better)."""
    before = float(np.var(before_load))
    after = float(np.var(after_load))
    if before <= 1e-9:
        return 0.0
    return float(((before - after) / before) * 100.0)


def peak_load_reduction(before_load: np.ndarray, after_load: np.ndarray) -> float:
    """Percent reduction in max hourly load."""
    before = peak_load(before_load)
    after = peak_load(after_load)
    if before <= 1e-9:
        return 0.0
    return float(((before - after) / before) * 100.0)


def build_metrics(
    before_load: np.ndarray,
    after_load: np.ndarray,
    stress: np.ndarray,
    jobs_shifted: int,
) -> dict:
    """Bundle standard optimization metrics."""
    return {
        "peak_overlap_reduction": round(peak_overlap_reduction(before_load, after_load, stress), 2),
        "jobs_shifted": int(jobs_shifted),
        "grid_friendliness_score_before": round(grid_friendliness_score(before_load, stress), 2),
        "grid_friendliness_score_after": round(grid_friendliness_score(after_load, stress), 2),
        "load_variance_reduction": round(load_variance_reduction(before_load, after_load), 2),
        "peak_load_reduction": round(peak_load_reduction(before_load, after_load), 2),
    }
