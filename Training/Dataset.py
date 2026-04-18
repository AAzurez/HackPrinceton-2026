"""
GridShift DC dataset utilities.

Builds a long-format hourly dataset for:
- PJM grid demand proxy (`grid_demand_mw`)
- synthetic data center load (`dc_load_mw` / `target`)
- calendar and operational covariates
- sliding windows for Chronos-2 (context=168, horizon=24 by default)
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

CONTEXT_LEN_DEFAULT = 168
HORIZON_DEFAULT = 24

FUTURE_COVARIATE_COLS = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_holiday",
]

# Chronos-2 dict API requires keys(future_covariates) subset keys(past_covariates).
PAST_COVARIATE_COLS = [
    "grid_demand_mw",
    "workload_pressure_index",
    "critical_workload_ratio",
    "batch_workload_ratio",
    "cooling_overhead_ratio",
    "shiftable_load_mw",
    *FUTURE_COVARIATE_COLS,
]

RATIO_COLS = [
    "workload_pressure_index",
    "critical_workload_ratio",
    "batch_workload_ratio",
    "cooling_overhead_ratio",
]


def _infer_pjm_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Infer timestamp and demand columns from a PJM-like CSV."""
    ts_candidates: list[tuple[float, str]] = []
    mw_candidates: list[tuple[float, str]] = []

    for col in df.columns:
        col_name = str(col).lower()

        ts_parsed = pd.to_datetime(df[col], errors="coerce")
        ts_ratio = float(ts_parsed.notna().mean())
        if ts_ratio >= 0.8:
            bonus = 0.2 if any(x in col_name for x in ["time", "date", "datetime", "timestamp"]) else 0.0
            ts_candidates.append((ts_ratio + bonus, col))

        mw_parsed = pd.to_numeric(df[col], errors="coerce")
        mw_ratio = float(mw_parsed.notna().mean())
        if mw_ratio >= 0.8:
            bonus = 0.2 if any(x in col_name for x in ["mw", "load", "demand", "pjm"]) else 0.0
            mw_candidates.append((mw_ratio + bonus, col))

    if not ts_candidates:
        raise ValueError("Could not infer timestamp column from CSV.")

    ts_candidates.sort(reverse=True)
    timestamp_col = ts_candidates[0][1]

    mw_candidates = [x for x in mw_candidates if x[1] != timestamp_col]
    if mw_candidates:
        mw_candidates.sort(reverse=True)
        demand_col = mw_candidates[0][1]
    else:
        fallback = [c for c in df.columns if c != timestamp_col]
        if not fallback:
            raise ValueError("Could not infer demand column from CSV.")
        demand_col = fallback[0]

    return timestamp_col, demand_col


def load_pjm_data(
    csv_path: str,
    timestamp_col: str | None = None,
    demand_col: str | None = None,
    forward_fill_limit_hours: int = 3,
) -> pd.DataFrame:
    """
    Load PJM demand CSV and enforce hourly cadence.

    Returns columns:
    - timestamp (datetime64[ns])
    - grid_demand_mw (float64)
    """
    df = pd.read_csv(csv_path)

    if timestamp_col is None or demand_col is None:
        inferred_ts, inferred_mw = _infer_pjm_columns(df)
        timestamp_col = timestamp_col or inferred_ts
        demand_col = demand_col or inferred_mw

    if timestamp_col not in df.columns:
        raise ValueError(f"Timestamp column '{timestamp_col}' not found.")
    if demand_col not in df.columns:
        raise ValueError(f"Demand column '{demand_col}' not found.")

    out = df[[timestamp_col, demand_col]].copy()
    out.columns = ["timestamp", "grid_demand_mw"]
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["grid_demand_mw"] = pd.to_numeric(out["grid_demand_mw"], errors="coerce")
    out = out.dropna(subset=["timestamp", "grid_demand_mw"])

    # Collapse duplicate timestamps by mean (helps with DST/source quirks).
    out = out.groupby("timestamp", as_index=False)["grid_demand_mw"].mean()
    out = out.sort_values("timestamp").reset_index(drop=True)

    full_idx = pd.date_range(out["timestamp"].min(), out["timestamp"].max(), freq="h")
    out = out.set_index("timestamp").reindex(full_idx)

    missing = out["grid_demand_mw"].isna()
    max_gap = int(missing.astype(int).groupby((~missing).cumsum()).sum().max() or 0)
    if max_gap > forward_fill_limit_hours:
        warnings.warn(
            f"PJM data has gaps up to {max_gap} hours. Forward fill may add artifacts.",
            stacklevel=2,
        )

    out["grid_demand_mw"] = out["grid_demand_mw"].ffill(limit=forward_fill_limit_hours)
    out = out.dropna(subset=["grid_demand_mw"])
    out = out.reset_index().rename(columns={"index": "timestamp"})

    return out


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add hourly/day/weekend/US federal holiday flags."""
    from pandas.tseries.holiday import USFederalHolidayCalendar

    out = df.copy()
    ts = out["timestamp"]

    out["hour_of_day"] = ts.dt.hour.astype(np.int16)
    out["day_of_week"] = ts.dt.dayofweek.astype(np.int16)
    out["is_weekend"] = (out["day_of_week"] >= 5).astype(np.int16)

    cal = USFederalHolidayCalendar()
    holidays = cal.holidays(start=ts.min(), end=ts.max())
    out["is_holiday"] = ts.dt.normalize().isin(holidays).astype(np.int16)

    return out


def generate_synthetic_dc_load(
    grid_df: pd.DataFrame,
    seed: int = 42,
    baseline_bounds_mw: tuple[float, float] = (8.0, 12.0),
) -> pd.DataFrame:
    """
    Generate synthetic but realistic data center load and covariates.

    Construction summary:
    - always-on baseline (8-12 MW)
    - weakly correlated component from normalized PJM demand
    - daily business-hour shape + non-flat nighttime behavior
    - batch/AI bursts during 22:00-02:00 on roughly 3 nights/week
    - AR(1) structured noise
    - cooling overhead ratio increases with load and mild seasonality
    """
    required = {"timestamp", "grid_demand_mw"}
    missing = required - set(grid_df.columns)
    if missing:
        raise ValueError(f"grid_df is missing required columns: {sorted(missing)}")

    rng = np.random.default_rng(seed)
    out = grid_df.sort_values("timestamp").reset_index(drop=True).copy()

    ts = out["timestamp"]
    hour = ts.dt.hour.to_numpy()
    dow = ts.dt.dayofweek.to_numpy()
    doy = ts.dt.dayofyear.to_numpy()
    n = len(out)
    idx = np.arange(n, dtype=float)

    grid = out["grid_demand_mw"].to_numpy(dtype=float)
    grid_z = (grid - grid.mean()) / (grid.std() + 1e-8)

    baseline = float(rng.uniform(*baseline_bounds_mw))
    weekly_drift = 0.9 * np.sin(2.0 * np.pi * idx / (7.0 * 24.0) + rng.uniform(0, 2 * np.pi))

    day_cycle = 1.2 * np.sin(2.0 * np.pi * (hour - 8) / 24.0)
    day_cycle = np.where(day_cycle > 0, day_cycle, 0.35 * day_cycle)
    business_bump = ((hour >= 8) & (hour <= 18)).astype(float) * 0.6
    weekend_effect = np.where(dow >= 5, -0.4, 0.0)

    grid_component = 1.5 * grid_z

    batch_spike = np.zeros(n, dtype=float)
    unique_dates = pd.Index(ts.dt.normalize().unique())
    batch_night_mask = rng.random(len(unique_dates)) < (3.0 / 7.0)
    batch_night_map = pd.Series(batch_night_mask, index=unique_dates)
    is_batch_night = ts.dt.normalize().map(batch_night_map).fillna(False).to_numpy(dtype=bool)
    in_batch_window = (hour >= 22) | (hour <= 2)
    batch_hours = is_batch_night & in_batch_window
    batch_spike[batch_hours] = rng.uniform(1.5, 4.8, size=int(batch_hours.sum()))

    eps = rng.normal(0.0, 0.35, size=n)
    ar_noise = np.zeros(n, dtype=float)
    ar_noise[0] = eps[0]
    for i in range(1, n):
        ar_noise[i] = 0.65 * ar_noise[i - 1] + eps[i]

    it_load = baseline + weekly_drift + day_cycle + business_bump + weekend_effect + grid_component + batch_spike + ar_noise
    it_load = np.clip(it_load, baseline_bounds_mw[0], 24.0)

    load_norm = (it_load - it_load.min()) / (it_load.max() - it_load.min() + 1e-8)
    seasonal_heat = (np.sin(2 * np.pi * (doy - 172) / 365.25) + 1.0) / 2.0
    cooling_overhead_ratio = 0.12 + 0.09 * load_norm + 0.03 * seasonal_heat + rng.normal(0, 0.005, n)
    cooling_overhead_ratio = np.clip(cooling_overhead_ratio, 0.12, 0.30)

    dc_load_mw = it_load * (1.0 + cooling_overhead_ratio)
    dc_load_mw = np.clip(dc_load_mw, baseline_bounds_mw[0], 32.0)

    pressure_smooth = pd.Series(dc_load_mw).rolling(window=6, min_periods=1).mean().to_numpy()
    workload_pressure_index = (pressure_smooth - pressure_smooth.min()) / (pressure_smooth.max() - pressure_smooth.min() + 1e-8)

    critical_ratio = 0.67 + rng.normal(0.0, 0.03, n) - 0.06 * batch_hours.astype(float)
    critical_ratio = np.clip(critical_ratio, 0.50, 0.80)

    batch_ratio = 0.16 + 0.18 * workload_pressure_index + 0.12 * batch_hours.astype(float) + rng.normal(0.0, 0.025, n)
    batch_ratio = np.clip(batch_ratio, 0.05, 0.50)
    batch_ratio = np.minimum(batch_ratio, np.clip(1.0 - critical_ratio + 0.05, 0.08, 0.50))
    batch_ratio = np.clip(batch_ratio, 0.05, 0.50)

    shiftable_load_mw = dc_load_mw * batch_ratio

    out["dc_load_mw"] = dc_load_mw.astype(float)
    out["workload_pressure_index"] = workload_pressure_index.astype(float)
    out["critical_workload_ratio"] = critical_ratio.astype(float)
    out["batch_workload_ratio"] = batch_ratio.astype(float)
    out["cooling_overhead_ratio"] = cooling_overhead_ratio.astype(float)
    out["shiftable_load_mw"] = shiftable_load_mw.astype(float)

    return out


def build_dataset(
    csv_path: str,
    facility_id: str = "dc_01",
    seed: int = 42,
    timestamp_col: str | None = None,
    demand_col: str | None = None,
) -> pd.DataFrame:
    """End-to-end dataset builder matching required long format schema."""
    grid_df = load_pjm_data(csv_path, timestamp_col=timestamp_col, demand_col=demand_col)
    grid_df = add_calendar_features(grid_df)
    full_df = generate_synthetic_dc_load(grid_df, seed=seed)

    full_df["id"] = facility_id
    full_df["target"] = full_df["dc_load_mw"]

    for col in RATIO_COLS:
        full_df[col] = full_df[col].clip(0.0, 1.0)

    ordered_cols = [
        "id",
        "timestamp",
        "target",
        "grid_demand_mw",
        "hour_of_day",
        "day_of_week",
        "is_weekend",
        "is_holiday",
        "workload_pressure_index",
        "critical_workload_ratio",
        "batch_workload_ratio",
        "cooling_overhead_ratio",
        "shiftable_load_mw",
        "dc_load_mw",
    ]
    return full_df[ordered_cols].reset_index(drop=True)


def normalize_features(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Standard-scale continuous features and keep ratios in [0, 1].

    Scaled columns:
    - target (and dc_load_mw with the same stats)
    - grid_demand_mw
    - shiftable_load_mw
    """
    out = df.copy()
    scalers: dict[str, dict[str, float]] = {}

    target_mean = float(out["dc_load_mw"].mean())
    target_std = float(out["dc_load_mw"].std() + 1e-8)

    out["target"] = (out["target"] - target_mean) / target_std
    out["dc_load_mw"] = (out["dc_load_mw"] - target_mean) / target_std
    scalers["target"] = {"mean": target_mean, "std": target_std}
    scalers["dc_load_mw"] = {"mean": target_mean, "std": target_std}

    for col in ["grid_demand_mw", "shiftable_load_mw"]:
        mean = float(out[col].mean())
        std = float(out[col].std() + 1e-8)
        out[col] = (out[col] - mean) / std
        scalers[col] = {"mean": mean, "std": std}

    for col in RATIO_COLS:
        out[col] = out[col].clip(0.0, 1.0)

    return out, scalers


def create_windows(
    df: pd.DataFrame,
    context_len: int = CONTEXT_LEN_DEFAULT,
    horizon: int = HORIZON_DEFAULT,
    stride: int = 24,
    target_col: str = "target",
    past_covariate_cols: list[str] | None = None,
    future_covariate_cols: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    """
    Create Chronos-2 dict API windows.

    Returns:
    - windows: list[dict], each with target, past_covariates, future_covariates
    - future_targets: list[np.ndarray], shape (horizon,)
    """
    if past_covariate_cols is None:
        past_covariate_cols = PAST_COVARIATE_COLS
    if future_covariate_cols is None:
        future_covariate_cols = FUTURE_COVARIATE_COLS

    if not set(future_covariate_cols).issubset(set(past_covariate_cols)):
        raise ValueError(
            "Chronos-2 requires future_covariates keys to be a subset of past_covariates keys."
        )

    required_cols = {"id", "timestamp", target_col, *past_covariate_cols, *future_covariate_cols}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for windowing: {sorted(missing)}")

    windows: list[dict[str, Any]] = []
    future_targets: list[np.ndarray] = []

    # Group by id so the helper supports multi-series datasets.
    for _, grp in df.groupby("id", sort=False):
        g = grp.sort_values("timestamp").reset_index(drop=True)
        n = len(g)
        for start in range(0, n - context_len - horizon + 1, stride):
            ctx_end = start + context_len
            fut_end = ctx_end + horizon

            context = g.iloc[start:ctx_end]
            future = g.iloc[ctx_end:fut_end]

            window = {
                "target": context[target_col].to_numpy(dtype=np.float32),
                "past_covariates": {
                    col: context[col].to_numpy(dtype=np.float32) for col in past_covariate_cols
                },
                "future_covariates": {
                    col: future[col].to_numpy(dtype=np.float32) for col in future_covariate_cols
                },
            }
            windows.append(window)
            future_targets.append(future[target_col].to_numpy(dtype=np.float32))

    if not windows:
        raise ValueError("No windows created. Check context/horizon vs dataset length.")

    return windows, future_targets


def window_to_dataframes(
    df: pd.DataFrame,
    start: int,
    context_len: int = CONTEXT_LEN_DEFAULT,
    horizon: int = HORIZON_DEFAULT,
    target_col: str = "target",
    past_covariate_cols: list[str] | None = None,
    future_covariate_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """
    Build context_df and future_df for Chronos-2 predict_df.

    Notes:
    - context_df has `context_len` historical rows.
    - future_df has exactly `horizon` rows.
    """
    if past_covariate_cols is None:
        past_covariate_cols = PAST_COVARIATE_COLS
    if future_covariate_cols is None:
        future_covariate_cols = FUTURE_COVARIATE_COLS

    ctx_end = start + context_len
    fut_end = ctx_end + horizon

    if fut_end > len(df):
        raise ValueError("Requested window exceeds dataframe length.")

    context_df = df.iloc[start:ctx_end][["id", "timestamp", target_col] + past_covariate_cols].copy()
    future_df = df.iloc[ctx_end:fut_end][["id", "timestamp"] + future_covariate_cols].copy()
    actual = df.iloc[ctx_end:fut_end][target_col].to_numpy(dtype=np.float32)

    return context_df, future_df, actual

