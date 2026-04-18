"""Rule-based explanations for scheduling decisions."""

from __future__ import annotations

import logging


class ExplanationService:
    """Generates concise, deterministic explanation strings without external LLMs."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def job_reason(
        self,
        *,
        priority: str,
        old_start_hour: int,
        new_start_hour: int,
        stress_before: float,
        stress_after: float,
    ) -> str:
        if priority == "critical":
            return "Kept in place because workload is marked critical and cannot be shifted."

        if old_start_hour == new_start_hour:
            return "Kept in place because alternative windows did not improve stress overlap while meeting constraints."

        if stress_after < stress_before:
            return "Moved out of a higher stress window while keeping completion before deadline."

        if new_start_hour > old_start_hour:
            return "Shifted later to reduce overlap with the evening peak while satisfying timing constraints."

        return "Shifted earlier to a lower stress window while respecting duration and deadline."

    def summary(self, schedule_changes: list[dict], high_stress_hours: list[int]) -> str:
        shifted = [c for c in schedule_changes if c.get("old_start_hour") != c.get("new_start_hour")]
        if not shifted:
            return "No flexible jobs were moved; current schedule already satisfies constraints with minimal stress overlap."

        count = len(shifted)
        stress_window = ", ".join(str(h) for h in high_stress_hours[:4])
        return (
            f"{count} flexible jobs were shifted away from high-stress hours "
            f"({stress_window}) to lower-impact windows."
        )
