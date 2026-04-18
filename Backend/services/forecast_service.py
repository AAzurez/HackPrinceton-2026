"""Chronos-2 forecast service with startup model loading and safe fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

from config import AppConfig
from utils.preprocessing import build_future_timestamps, history_to_dataframe, validate_min_history


class ForecastService:
    """Wraps Chronos-2 inference for backend API usage."""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.pipeline = None
        self.model_loaded = False
        self.model_error: str | None = None
        self._load_model_once()

    def _load_model_once(self) -> None:
        model_dir = self.config.model_dir
        try:
            if not model_dir.exists():
                raise FileNotFoundError(f"Model directory does not exist: {model_dir}")

            import torch
            from chronos import Chronos2Pipeline

            prefer_device = os.getenv("GRIDSHIFT_MODEL_DEVICE", "cuda")
            if prefer_device == "cuda" and not torch.cuda.is_available():
                prefer_device = "cpu"

            dtype = torch.float16 if prefer_device == "cuda" else torch.float32

            self.pipeline = Chronos2Pipeline.from_pretrained(
                str(model_dir),
                device_map=prefer_device,
                dtype=dtype,
            )
            self.model_loaded = True
            self.logger.info("Chronos-2 model loaded from %s on %s", model_dir, prefer_device)
        except Exception as exc:  # noqa: BLE001
            self.model_loaded = False
            self.model_error = str(exc)
            self.logger.exception("Failed to load Chronos-2 model. Forecast fallback will be used.")

    def forecast(self, series_id: str, history: list[dict[str, Any]], horizon_hours: int) -> dict[str, Any]:
        """Forecast next horizon_hours load values from history."""
        df = history_to_dataframe(history)
        validate_min_history(df, self.config.min_history_hours)

        if self.model_loaded:
            try:
                forecast = self._forecast_with_model(series_id=series_id, history_df=df, horizon_hours=horizon_hours)
                return {
                    "series_id": series_id,
                    "forecast": forecast,
                    "model_used": "chronos2_finetuned",
                }
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Model inference failed, falling back to heuristic forecast: %s", exc)

        forecast = self._fallback_forecast(df, horizon_hours)
        return {
            "series_id": series_id,
            "forecast": forecast,
            "model_used": "fallback_heuristic",
            "warning": self.model_error or "Chronos model unavailable; using fallback forecast.",
        }

    def _forecast_with_model(self, series_id: str, history_df: pd.DataFrame, horizon_hours: int) -> list[dict[str, Any]]:
        context_df = pd.DataFrame(
            {
                "id": series_id,
                "timestamp": history_df["timestamp"],
                "target": history_df["load_mw"],
            }
        )

        pred_df = self.pipeline.predict_df(
            context_df,
            prediction_length=horizon_hours,
            id_column="id",
            timestamp_column="timestamp",
            target="target",
            quantile_levels=[0.1, 0.5, 0.9],
            batch_size=256,
        )

        if "target_name" in pred_df.columns:
            pred_df = pred_df[pred_df["target_name"] == "target"]

        pred_df = pred_df.sort_values("timestamp").reset_index(drop=True)

        if len(pred_df) != horizon_hours:
            raise RuntimeError(
                f"Chronos returned {len(pred_df)} rows; expected {horizon_hours}."
            )

        result = []
        for _, row in pred_df.iterrows():
            result.append(
                {
                    "timestamp": pd.to_datetime(row["timestamp"]).isoformat(),
                    "predicted_load_mw": float(row["predictions"]),
                    "q10": float(row.get("0.1", np.nan)),
                    "q90": float(row.get("0.9", np.nan)),
                }
            )
        return result

    def _fallback_forecast(self, history_df: pd.DataFrame, horizon_hours: int) -> list[dict[str, Any]]:
        series = history_df["load_mw"].to_numpy(dtype=float)
        last_ts = pd.to_datetime(history_df["timestamp"].iloc[-1]).to_pydatetime()
        future_ts = build_future_timestamps(last_ts, horizon_hours)

        # Seasonal naive: repeat same hour-of-day from previous 24h, plus mild trend.
        if len(series) >= 24:
            day_pattern = np.resize(series[-24:], horizon_hours)
        else:
            day_pattern = np.full(horizon_hours, series[-1], dtype=float)

        if len(series) >= 48:
            trend = float(np.mean(series[-24:]) - np.mean(series[-48:-24]))
        else:
            trend = 0.0

        trend_component = np.linspace(0.0, trend * 0.25, horizon_hours)
        pred = np.maximum(day_pattern + trend_component, 0.0)

        return [
            {
                "timestamp": ts.isoformat(),
                "predicted_load_mw": float(val),
            }
            for ts, val in zip(future_ts, pred)
        ]
