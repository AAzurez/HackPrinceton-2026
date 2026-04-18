"""Preprocessing helpers for forecasting and optimization payloads."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd


class PreprocessingError(ValueError):
    """Raised when payload preprocessing fails."""


def history_to_dataframe(history: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert forecast history payload to a clean hourly DataFrame."""
    if not history:
        raise PreprocessingError("history is empty")

    df = pd.DataFrame(history)
    required_cols = {"timestamp", "load_mw"}
    missing = required_cols - set(df.columns)
    if missing:
        raise PreprocessingError(f"history missing required fields: {sorted(missing)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["load_mw"] = pd.to_numeric(df["load_mw"], errors="coerce")
    df = df.dropna(subset=["timestamp", "load_mw"]).copy()
    if df.empty:
        raise PreprocessingError("history has no valid timestamp/load_mw rows")

    # Collapse duplicate timestamps and enforce sorted hourly index.
    df = df.groupby("timestamp", as_index=False)["load_mw"].mean()
    df = df.sort_values("timestamp").reset_index(drop=True)

    full_idx = pd.date_range(df["timestamp"].min(), df["timestamp"].max(), freq="h")
    df = df.set_index("timestamp").reindex(full_idx)
    df["load_mw"] = df["load_mw"].interpolate(limit_direction="both")
    df = df.reset_index().rename(columns={"index": "timestamp"})

    return df


def validate_min_history(df: pd.DataFrame, min_history_hours: int) -> None:
    """Ensure enough history for model context."""
    if len(df) < min_history_hours:
        raise PreprocessingError(
            f"history must include at least {min_history_hours} hourly points; got {len(df)}"
        )


def build_future_timestamps(last_timestamp: datetime, horizon: int) -> list[datetime]:
    """Build hourly timestamps after the last observed point."""
    return [last_timestamp + timedelta(hours=i) for i in range(1, horizon + 1)]


def _hour_to_index(value: Any, fallback_idx: int) -> int:
    """Parse hour field from int/string/datetime to [0, 23]."""
    if isinstance(value, int):
        if 0 <= value <= 23:
            return value
        raise PreprocessingError(f"hour integer out of range [0, 23]: {value}")

    if isinstance(value, str):
        if value.isdigit():
            hour = int(value)
            if 0 <= hour <= 23:
                return hour
            raise PreprocessingError(f"hour string out of range [0, 23]: {value}")
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            raise PreprocessingError(f"could not parse hour value: {value}")
        return int(parsed.hour)

    if hasattr(value, "hour"):
        return int(value.hour)

    # Fallback to index position when input omits explicit hour semantics.
    hour = fallback_idx % 24
    return hour


def profile_to_dataframe(profile: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert optimization profile payload to a normalized 24-hour DataFrame."""
    if not profile:
        raise PreprocessingError("profile is empty")

    rows = []
    for idx, point in enumerate(profile):
        if "load_mw" not in point:
            raise PreprocessingError("each profile row must include load_mw")
        hour_idx = _hour_to_index(point.get("hour"), idx)
        load = float(point["load_mw"])
        stress = float(point.get("grid_stress", 0.0))
        if load < 0:
            raise PreprocessingError("load_mw must be non-negative")
        if stress < 0 or stress > 1:
            raise PreprocessingError("grid_stress must be in [0, 1]")
        rows.append({"hour": hour_idx, "load_mw": load, "grid_stress": stress})

    df = pd.DataFrame(rows)

    if len(df) != 24:
        raise PreprocessingError(f"profile must contain 24 rows; got {len(df)}")

    if df["hour"].nunique() != 24:
        raise PreprocessingError("profile must include each hour 0-23 exactly once")

    df = df.sort_values("hour").reset_index(drop=True)
    return df
