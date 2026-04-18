"""
GridShift DC Chronos-2 training/inference entrypoint.

What this script does:
1) loads PJM hourly demand CSV
2) generates synthetic data center demand/covariates
3) normalizes continuous features
4) creates sliding windows (context=168, horizon=24)
5) runs Chronos-2 zero-shot forecast on one sample
6) optionally runs Chronos-2 fine-tuning skeleton
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset

# Ensure Training/ is importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from Dataset import (
    CONTEXT_LEN_DEFAULT,
    FUTURE_COVARIATE_COLS,
    HORIZON_DEFAULT,
    PAST_COVARIATE_COLS,
    build_dataset,
    create_windows,
    normalize_features,
    window_to_dataframes,
)


class WindowDataset(Dataset):
    """PyTorch dataset wrapper around Chronos-2 window dicts."""

    def __init__(self, windows: list[dict[str, Any]], future_targets: list[np.ndarray]) -> None:
        if len(windows) != len(future_targets):
            raise ValueError("windows and future_targets must have the same length")
        self.windows = windows
        self.future_targets = future_targets

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        return {
            "window": self.windows[idx],
            "future_target": torch.tensor(self.future_targets[idx], dtype=torch.float32),
        }


def _collate_window_batch(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "windows": [x["window"] for x in batch],
        "future_targets": torch.stack([x["future_target"] for x in batch], dim=0),
    }


def make_train_dataloader(
    windows: list[dict[str, Any]],
    future_targets: list[np.ndarray],
    batch_size: int = 16,
    shuffle: bool = True,
) -> DataLoader:
    """
    Create a train dataloader for future fine-tuning use.

    Batch format:
    - windows: list[dict] (Chronos-2 dict input format)
    - future_targets: Tensor[batch_size, horizon]
    """
    dataset = WindowDataset(windows, future_targets)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=_collate_window_batch,
        num_workers=0,
    )


def load_model(
    model_name: str = "amazon/chronos-2",
    device: str = "cpu",
    torch_dtype: str = "float32",
):
    """Load Chronos-2 pipeline from Hugging Face."""
    from chronos import Chronos2Pipeline

    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }

    if torch_dtype not in dtype_map:
        raise ValueError(f"Unsupported torch_dtype: {torch_dtype}")

    pipeline = Chronos2Pipeline.from_pretrained(
        model_name,
        device_map=device,
        torch_dtype=dtype_map[torch_dtype],
    )
    return pipeline


def predict_zero_shot_df(
    pipeline,
    context_df: pd.DataFrame,
    future_df: pd.DataFrame,
    prediction_length: int = HORIZON_DEFAULT,
    quantile_levels: list[float] | None = None,
) -> pd.DataFrame:
    """Run Chronos-2 zero-shot forecasting via DataFrame API."""
    if quantile_levels is None:
        quantile_levels = [0.1, 0.5, 0.9]

    pred_df = pipeline.predict_df(
        context_df,
        future_df=future_df,
        prediction_length=prediction_length,
        quantile_levels=quantile_levels,
        id_column="id",
        timestamp_column="timestamp",
        target="target",
    )
    return pred_df


def predict_zero_shot_tensor(
    pipeline,
    window: dict[str, Any],
    prediction_length: int = HORIZON_DEFAULT,
    quantile_levels: list[float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Run Chronos-2 zero-shot forecasting via dict API on a single window.

    Returns:
    - quantiles: shape (n_targets, prediction_length, n_quantiles)
    - mean: shape (n_targets, prediction_length)
    """
    if quantile_levels is None:
        quantile_levels = [0.1, 0.5, 0.9]

    quantiles_list, mean_list = pipeline.predict_quantiles(
        [window],
        prediction_length=prediction_length,
        quantile_levels=quantile_levels,
    )

    quantiles = quantiles_list[0].detach().cpu().numpy()
    mean = mean_list[0].detach().cpu().numpy()
    return quantiles, mean


def train_val_split(
    windows: list[dict[str, Any]],
    future_targets: list[np.ndarray],
    val_frac: float = 0.15,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[np.ndarray], list[np.ndarray]]:
    """Chronological train/validation split over windows."""
    n = len(windows)
    if n <= 1:
        return windows, [], future_targets, []

    split = int(n * (1.0 - val_frac))
    split = max(1, min(split, n - 1))

    return (
        windows[:split],
        windows[split:],
        future_targets[:split],
        future_targets[split:],
    )


def finetune_model(
    pipeline,
    train_windows: list[dict[str, Any]],
    val_windows: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
):
    """
    Fine-tune Chronos-2 using pipeline.fit.

    TODO: tune these for your hackathon setup.
    - learning_rate
    - num_steps
    - batch_size
    - finetune_mode (lora/full)
    """
    if config is None:
        config = {}

    fit_kwargs: dict[str, Any] = {
        "inputs": train_windows,
        "prediction_length": config.get("prediction_length", HORIZON_DEFAULT),
        "num_steps": config.get("num_steps", 400),
        "learning_rate": config.get("learning_rate", 1e-4),
        "batch_size": config.get("batch_size", 16),
        "finetune_mode": config.get("finetune_mode", "lora"),
        "logging_steps": config.get("logging_steps", 50),
    }

    if val_windows:
        fit_kwargs["validation_inputs"] = val_windows

    print(
        "[finetune] "
        f"mode={fit_kwargs['finetune_mode']} "
        f"steps={fit_kwargs['num_steps']} "
        f"lr={fit_kwargs['learning_rate']} "
        f"batch={fit_kwargs['batch_size']}"
    )

    return pipeline.fit(**fit_kwargs)


def inverse_scale(values: np.ndarray, scalers: dict[str, dict[str, float]], col: str = "target") -> np.ndarray:
    """Undo standardization for a specific column."""
    return values * scalers[col]["std"] + scalers[col]["mean"]


def _extract_quantile_column(pred_df: pd.DataFrame, q: float) -> np.ndarray:
    """Handle quantile column naming differences robustly."""
    candidates = [str(q), f"{q:.1f}", f"{q:.2f}"]
    for col in candidates:
        if col in pred_df.columns:
            return pred_df[col].to_numpy(dtype=float)
    raise KeyError(f"Could not find quantile column for q={q} in {list(pred_df.columns)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GridShift DC Chronos-2 pipeline")
    parser.add_argument("--csv_path", type=str, required=True, help="Path to PJM hourly CSV")
    parser.add_argument("--facility_id", type=str, default="dc_01")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--context_len", type=int, default=CONTEXT_LEN_DEFAULT)
    parser.add_argument("--horizon", type=int, default=HORIZON_DEFAULT)
    parser.add_argument("--stride", type=int, default=24)
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--torch_dtype", type=str, default="float32", choices=["float32", "float16", "bfloat16"])
    parser.add_argument("--model", type=str, default="amazon/chronos-2")
    parser.add_argument("--finetune", action="store_true")
    parser.add_argument("--ft_steps", type=int, default=2000, help="Fine-tune optimization steps")
    parser.add_argument("--ft_lr", type=float, default=1e-4, help="Fine-tune learning rate")
    parser.add_argument("--ft_batch_size", type=int, default=8, help="Fine-tune batch size")
    parser.add_argument("--ft_mode", type=str, default="full", choices=["lora", "full"], help="Fine-tune mode")
    parser.add_argument("--ft_val_frac", type=float, default=0.2, help="Validation split fraction")
    parser.add_argument("--ft_logging_steps", type=int, default=50, help="Logging frequency in training steps")
    parser.add_argument(
        "--ft_save_dir",
        type=str,
        default="artifacts/chronos2_gridshift_finetuned",
        help="Directory to save the fine-tuned model and metadata",
    )
    parser.add_argument("--plot_path", type=str, default="forecast_sanity_check.png")
    args = parser.parse_args()

    print("[1/7] Loading PJM data and generating synthetic DC load...")
    full_df = build_dataset(args.csv_path, facility_id=args.facility_id, seed=args.seed)
    corr = float(full_df["dc_load_mw"].corr(full_df["grid_demand_mw"]))
    print(f"  Rows: {len(full_df)}")
    print(f"  Date range: {full_df['timestamp'].min()} -> {full_df['timestamp'].max()}")
    print(f"  Corr(dc_load_mw, grid_demand_mw): {corr:.3f}")

    print("[2/7] Normalizing features...")
    scaled_df, scalers = normalize_features(full_df)

    print("[3/7] Creating sliding windows...")
    windows, future_targets = create_windows(
        scaled_df,
        context_len=args.context_len,
        horizon=args.horizon,
        stride=args.stride,
        target_col="target",
        past_covariate_cols=PAST_COVARIATE_COLS,
        future_covariate_cols=FUTURE_COVARIATE_COLS,
    )
    print(f"  Total windows: {len(windows)}")

    print("[4/7] Building train dataloader (fine-tuning skeleton)...")
    train_loader = make_train_dataloader(
        windows,
        future_targets,
        batch_size=args.ft_batch_size,
        shuffle=True,
    )
    first_batch = next(iter(train_loader))
    print(
        f"  One batch: windows={len(first_batch['windows'])}, "
        f"future_targets_shape={tuple(first_batch['future_targets'].shape)}"
    )

    print(f"[5/7] Loading model {args.model} on {args.device}...")
    pipeline = load_model(args.model, device=args.device, torch_dtype=args.torch_dtype)

    print("[6/7] Running zero-shot 24-hour forecast...")
    sample_idx = len(windows) // 2
    sample_start = sample_idx * args.stride

    context_df, future_df, actual_scaled = window_to_dataframes(
        scaled_df,
        start=sample_start,
        context_len=args.context_len,
        horizon=args.horizon,
        target_col="target",
        past_covariate_cols=PAST_COVARIATE_COLS,
        future_covariate_cols=FUTURE_COVARIATE_COLS,
    )

    pred_df = predict_zero_shot_df(
        pipeline,
        context_df=context_df,
        future_df=future_df,
        prediction_length=args.horizon,
        quantile_levels=[0.1, 0.5, 0.9],
    )

    if "target_name" in pred_df.columns:
        pred_df = pred_df[pred_df["target_name"] == "target"]

    pred_df = pred_df.sort_values("timestamp").reset_index(drop=True)
    if len(pred_df) != args.horizon:
        raise ValueError(f"Expected {args.horizon} predictions, got {len(pred_df)}")

    pred_scaled = pred_df["predictions"].to_numpy(dtype=float)
    q10_scaled = _extract_quantile_column(pred_df, 0.1)
    q90_scaled = _extract_quantile_column(pred_df, 0.9)

    pred_mw = inverse_scale(pred_scaled, scalers, "target")
    actual_mw = inverse_scale(actual_scaled, scalers, "target")
    q10_mw = inverse_scale(q10_scaled, scalers, "target")
    q90_mw = inverse_scale(q90_scaled, scalers, "target")

    print("\nHour | Timestamp           | Actual MW | Pred MW | Q10 MW | Q90 MW")
    print("-" * 70)
    for i in range(args.horizon):
        ts_str = pd.to_datetime(pred_df.loc[i, "timestamp"]).strftime("%Y-%m-%d %H:%M")
        print(
            f"{i:>4} | {ts_str} | {actual_mw[i]:>9.2f} | "
            f"{pred_mw[i]:>7.2f} | {q10_mw[i]:>6.2f} | {q90_mw[i]:>6.2f}"
        )

    mae = float(np.mean(np.abs(pred_mw - actual_mw)))
    rmse = float(np.sqrt(np.mean((pred_mw - actual_mw) ** 2)))
    print(f"\nMAE:  {mae:.3f} MW")
    print(f"RMSE: {rmse:.3f} MW")

    print("[7/7] Saving sanity-check plot...")
    try:
        import matplotlib.pyplot as plt

        plot_path = Path(args.plot_path)
        if not plot_path.is_absolute():
            plot_path = Path(args.csv_path).parent / plot_path

        ts = pd.to_datetime(pred_df["timestamp"])
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(ts, actual_mw, marker="o", label="Actual dc_load_mw")
        ax.plot(ts, pred_mw, marker="s", linestyle="--", label="Chronos-2 median")
        ax.fill_between(ts, q10_mw, q90_mw, alpha=0.2, label="Q10-Q90")
        ax.set_xlabel("Timestamp")
        ax.set_ylabel("dc_load_mw (MW)")
        ax.set_title("GridShift DC: 24h zero-shot forecast")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)
        print(f"  Plot saved to {plot_path}")
    except ImportError:
        print("  matplotlib not installed, skipping plot")

    if args.finetune:
        print("\n[FT] Running fine-tuning skeleton...")
        train_w, val_w, _, _ = train_val_split(windows, future_targets, val_frac=args.ft_val_frac)
        pipeline = finetune_model(
            pipeline,
            train_windows=train_w,
            val_windows=val_w,
            config={
                "prediction_length": args.horizon,
                "num_steps": args.ft_steps,
                "learning_rate": args.ft_lr,
                "batch_size": args.ft_batch_size,
                "finetune_mode": args.ft_mode,
                "logging_steps": args.ft_logging_steps,
            },
        )
        print("[FT] Fine-tuning complete.")

        save_dir = Path(args.ft_save_dir)
        if not save_dir.is_absolute():
            save_dir = Path(__file__).resolve().parent / save_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        pipeline.save_pretrained(save_dir)

        metadata = {
            "model_name": args.model,
            "context_len": args.context_len,
            "horizon": args.horizon,
            "past_covariates": PAST_COVARIATE_COLS,
            "future_covariates": FUTURE_COVARIATE_COLS,
            "scalers": scalers,
            "target_column": "target",
            "id_column": "id",
            "timestamp_column": "timestamp",
        }
        metadata_path = save_dir / "gridshift_metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        print(f"[FT] Saved fine-tuned model to: {save_dir}")
        print(f"[FT] Saved metadata to: {metadata_path}")


if __name__ == "__main__":
    main()

