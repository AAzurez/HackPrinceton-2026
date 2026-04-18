"""Application configuration for GridShift DC backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration loaded from env vars with sensible local defaults."""

    app_name: str
    host: str
    port: int
    debug: bool
    model_dir: Path
    log_level: str
    min_history_hours: int
    forecast_horizon_hours: int

    data_dir: Path
    demo_profile_path: Path
    demo_workloads_path: Path

    @staticmethod
    def from_env() -> "AppConfig":
        backend_dir = Path(__file__).resolve().parent
        repo_root = backend_dir.parent

        default_model_candidates = [
            repo_root / "Training" / "artifacts" / "chronos2_gridshift_full",
            backend_dir / "models" / "chronos2_finetuned",
        ]

        model_dir_env = os.getenv("GRIDSHIFT_MODEL_DIR")
        if model_dir_env:
            model_dir = Path(model_dir_env)
        else:
            model_dir = next((p for p in default_model_candidates if p.exists()), default_model_candidates[0])

        data_dir = backend_dir / "data"

        return AppConfig(
            app_name="GridShift DC Backend",
            host=os.getenv("GRIDSHIFT_HOST", "0.0.0.0"),
            port=int(os.getenv("GRIDSHIFT_PORT", "5000")),
            debug=os.getenv("GRIDSHIFT_DEBUG", "false").lower() == "true",
            model_dir=model_dir,
            log_level=os.getenv("GRIDSHIFT_LOG_LEVEL", "INFO"),
            min_history_hours=int(os.getenv("GRIDSHIFT_MIN_HISTORY_HOURS", "48")),
            forecast_horizon_hours=int(os.getenv("GRIDSHIFT_FORECAST_HORIZON", "24")),
            data_dir=data_dir,
            demo_profile_path=data_dir / "demo_profile.csv",
            demo_workloads_path=data_dir / "demo_workloads.json",
        )
