"""Demo scenario loading service."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from config import AppConfig


class ScenarioService:
    """Provides a built-in scenario for frontend demos."""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def get_demo_scenario(self) -> dict[str, Any]:
        """Load demo profile/workloads from local files."""
        profile_path = self.config.demo_profile_path
        workloads_path = self.config.demo_workloads_path

        if not profile_path.exists():
            raise FileNotFoundError(f"Demo profile not found: {profile_path}")
        if not workloads_path.exists():
            raise FileNotFoundError(f"Demo workloads not found: {workloads_path}")

        profile_df = pd.read_csv(profile_path)
        required_cols = {"hour", "load_mw", "grid_stress"}
        missing = required_cols - set(profile_df.columns)
        if missing:
            raise ValueError(f"Demo profile missing columns: {sorted(missing)}")

        profile = []
        for _, row in profile_df.iterrows():
            profile.append(
                {
                    "hour": str(row["hour"]),
                    "load_mw": float(row["load_mw"]),
                    "grid_stress": float(row["grid_stress"]),
                }
            )

        # Use utf-8-sig so demo files load even if saved with a UTF-8 BOM.
        with workloads_path.open("r", encoding="utf-8-sig") as f:
            workloads = json.load(f)

        if not isinstance(workloads, list):
            raise ValueError("Demo workloads file must be a JSON array")

        self.logger.info("Loaded demo scenario: %d profile rows, %d workloads", len(profile), len(workloads))

        return {"profile": profile, "workloads": workloads}
