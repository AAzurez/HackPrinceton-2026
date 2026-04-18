"""Pydantic request schemas for GridShift DC APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HistoryPoint(BaseModel):
    timestamp: datetime
    load_mw: float = Field(..., ge=0.0)
    grid_demand_mw: float | None = Field(default=None, ge=0.0)


class ForecastRequest(BaseModel):
    series_id: str = Field(..., min_length=1)
    history: list[HistoryPoint]
    horizon_hours: int = Field(default=24, ge=1, le=48)

    @field_validator("history")
    @classmethod
    def validate_history_not_empty(cls, history: list[HistoryPoint]) -> list[HistoryPoint]:
        if len(history) < 24:
            raise ValueError("history must contain at least 24 hourly points")
        return history


class ProfilePoint(BaseModel):
    hour: int | str | datetime
    load_mw: float = Field(..., ge=0.0)
    grid_stress: float = Field(default=0.0, ge=0.0, le=1.0)


class WorkloadPayload(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    duration_hours: int = Field(..., ge=1, le=24)
    earliest_start: int = Field(..., ge=0, le=23)
    latest_finish: int = Field(..., ge=0, le=24)
    priority: Literal["critical", "flexible"]
    power_mw: float = Field(..., gt=0.0)
    current_start_hour: int | None = Field(default=None, ge=0, le=23)
    start_hour: int | None = Field(default=None, ge=0, le=23)

    @model_validator(mode="after")
    def validate_window_capacity(self) -> "WorkloadPayload":
        # latest_finish is treated as an exclusive boundary.
        # Overnight windows are allowed (latest_finish < earliest_start).
        if self.latest_finish >= self.earliest_start:
            available_hours = self.latest_finish - self.earliest_start
        else:
            available_hours = (24 - self.earliest_start) + self.latest_finish

        if self.duration_hours > available_hours:
            raise ValueError(
                "duration_hours does not fit scheduling window; "
                "increase window or reduce duration"
            )
        return self


class OptimizeRequest(BaseModel):
    profile: list[ProfilePoint]
    workloads: list[WorkloadPayload]

    @model_validator(mode="after")
    def validate_profile_and_workloads(self) -> "OptimizeRequest":
        if len(self.profile) != 24:
            raise ValueError("profile must have exactly 24 hourly points")
        if not self.workloads:
            raise ValueError("workloads must contain at least one job")
        return self
