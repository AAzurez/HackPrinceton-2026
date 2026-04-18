"""Grid-aware workload optimization engine for GridShift DC.

This module provides two solvers behind a common interface:
- solve_with_cp_sat: OR-Tools CP-SAT (preferred)
- solve_with_greedy: deterministic heuristic fallback

The optimization objective balances:
1) stress overlap penalty (primary)
2) peak load penalty
3) movement penalty (schedule stability)
4) anti-bunching penalty for flexible load concentration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

# Objective weights (easy to tune for demos).
STRESS_WEIGHT = 100
PEAK_WEIGHT = 20
MOVEMENT_WEIGHT = 6
BUNCHING_WEIGHT = 8

DEFAULT_HORIZON = 24
MW_SCALE = 100  # keep CP-SAT integer model in centi-MW.
STRESS_SCALE = 1000


@dataclass(frozen=True)
class WorkloadSpec:
    """Normalized workload spec used by both solvers."""

    id: str
    name: str
    duration_hours: int
    earliest_start: int
    latest_finish: int
    priority: str
    power_mw: float
    current_start_hour: int
    candidate_starts: tuple[int, ...]


def _parse_hour_value(value: Any, horizon: int = DEFAULT_HORIZON) -> int:
    """Parse profile hour values from int / datetime string / datetime-like objects."""
    if isinstance(value, int):
        if 0 <= value < horizon:
            return value
        raise ValueError(f"hour must be in [0, {horizon - 1}], got {value}")

    if isinstance(value, str):
        if value.isdigit():
            hour = int(value)
            if 0 <= hour < horizon:
                return hour
        parsed = np.datetime64(value)
        hour = int(str(parsed).split("T")[1].split(":")[0])
        if 0 <= hour < horizon:
            return hour
        raise ValueError(f"could not parse hour from value: {value}")

    if hasattr(value, "hour"):
        hour = int(value.hour)
        if 0 <= hour < horizon:
            return hour
        raise ValueError(f"hour must be in [0, {horizon - 1}], got {hour}")

    raise ValueError(f"unsupported hour type: {type(value)}")


def _normalize_profile(profile: list[dict[str, Any]], horizon: int = DEFAULT_HORIZON) -> list[dict[str, float]]:
    """Normalize profile into sorted 24-hour rows with hour/load_mw/grid_stress."""
    if len(profile) != horizon:
        raise ValueError(f"profile must contain exactly {horizon} rows")

    rows = []
    for idx, point in enumerate(profile):
        if "load_mw" not in point:
            raise ValueError("profile row missing load_mw")
        hour = _parse_hour_value(point.get("hour", idx), horizon=horizon)
        load = float(point["load_mw"])
        stress = float(point.get("grid_stress", 0.0))
        if load < 0:
            raise ValueError("load_mw must be non-negative")
        if not (0.0 <= stress <= 1.0):
            raise ValueError("grid_stress must be in [0, 1]")
        rows.append({"hour": hour, "load_mw": load, "grid_stress": stress})

    unique_hours = {r["hour"] for r in rows}
    if len(unique_hours) != horizon:
        raise ValueError("profile must include each hour 0-23 exactly once")

    rows.sort(key=lambda r: r["hour"])
    return rows


def _circular_distance(a: int, b: int, horizon: int = DEFAULT_HORIZON) -> int:
    """Shortest distance between two hour slots on a circular clock."""
    diff = abs(a - b)
    return int(min(diff, horizon - diff))


def _job_hours(start_hour: int, duration_hours: int, horizon: int = DEFAULT_HORIZON) -> list[int]:
    """List occupied hour indices for a job."""
    return [int((start_hour + i) % horizon) for i in range(duration_hours)]


def get_candidate_start_hours(job: dict[str, Any], horizon: int = DEFAULT_HORIZON) -> list[int]:
    """Return valid start hours for a workload, including overnight windows.

    Assumptions:
    - earliest_start is in [0, horizon-1]
    - latest_finish is in [0, horizon] where horizon means end-of-day boundary
    - latest_finish is treated as an exclusive boundary (job must finish by this hour)
    - overnight windows are represented by latest_finish < earliest_start
    """
    duration = int(job["duration_hours"])
    earliest = int(job["earliest_start"])
    latest_finish = int(job["latest_finish"])

    if not (1 <= duration <= horizon):
        raise ValueError(f"duration_hours must be in [1, {horizon}] for job {job.get('id')}")
    if not (0 <= earliest < horizon):
        raise ValueError(f"earliest_start must be in [0, {horizon - 1}] for job {job.get('id')}")
    if not (0 <= latest_finish <= horizon):
        raise ValueError(f"latest_finish must be in [0, {horizon}] for job {job.get('id')}")

    # Convert scheduling window into an absolute timeline segment.
    latest_abs = latest_finish
    if latest_finish < earliest:
        latest_abs += horizon

    # Special case for full-day window representation like earliest=0 latest=24.
    if latest_finish == horizon and earliest == 0 and duration == horizon:
        return [0]

    last_start_abs = latest_abs - duration
    if last_start_abs < earliest:
        return []

    starts_abs = range(earliest, last_start_abs + 1)

    starts_mod = []
    seen: set[int] = set()
    for start_abs in starts_abs:
        start_mod = int(start_abs % horizon)
        if start_mod not in seen:
            starts_mod.append(start_mod)
            seen.add(start_mod)

    return starts_mod


def _default_current_start(job: dict[str, Any], candidates: list[int], horizon: int = DEFAULT_HORIZON) -> int:
    """Resolve current start with backward compatibility for start_hour field."""
    preferred = job.get("current_start_hour", job.get("start_hour", job.get("earliest_start", 0)))
    current = int(preferred)
    if current < 0 or current >= horizon:
        current = int(job.get("earliest_start", 0))
    if current in candidates:
        return current
    return candidates[0] if candidates else current


def _normalize_workloads(workloads: list[dict[str, Any]], horizon: int = DEFAULT_HORIZON) -> list[WorkloadSpec]:
    """Normalize workload payload into validated WorkloadSpec records."""
    specs: list[WorkloadSpec] = []
    seen_ids: set[str] = set()

    for raw in workloads:
        job_id = str(raw.get("id", "")).strip()
        if not job_id:
            raise ValueError("Each workload must include a non-empty id")
        if job_id in seen_ids:
            raise ValueError(f"Duplicate workload id: {job_id}")
        seen_ids.add(job_id)

        priority = str(raw.get("priority", "")).lower()
        if priority not in {"critical", "flexible"}:
            raise ValueError(f"Invalid priority for job {job_id}: {priority}")

        power = float(raw.get("power_mw", 0.0))
        if power <= 0:
            raise ValueError(f"power_mw must be > 0 for job {job_id}")

        candidates = get_candidate_start_hours(raw, horizon=horizon)
        if not candidates:
            raise ValueError(
                f"Invalid workload payload: job {job_id} has no feasible start time "
                "for its duration/window constraints."
            )

        current = _default_current_start(raw, candidates, horizon=horizon)

        specs.append(
            WorkloadSpec(
                id=job_id,
                name=str(raw.get("name", job_id)),
                duration_hours=int(raw["duration_hours"]),
                earliest_start=int(raw["earliest_start"]),
                latest_finish=int(raw["latest_finish"]),
                priority=priority,
                power_mw=power,
                current_start_hour=current,
                candidate_starts=tuple(candidates),
            )
        )

    return specs


def _build_assignment_records(
    specs: list[WorkloadSpec],
    schedule_map: dict[str, int],
    horizon: int = DEFAULT_HORIZON,
) -> list[dict[str, Any]]:
    """Convert schedule map to assignment records expected by API output/helpers."""
    by_id = {s.id: s for s in specs}
    records: list[dict[str, Any]] = []
    for job_id, start in schedule_map.items():
        spec = by_id[job_id]
        end_hour = int((start + spec.duration_hours) % horizon)
        records.append(
            {
                "job_id": spec.id,
                "job_name": spec.name,
                "priority": spec.priority,
                "duration_hours": int(spec.duration_hours),
                "power_mw": float(spec.power_mw),
                "start_hour": int(start),
                "end_hour": end_hour,
                "current_start_hour": int(spec.current_start_hour),
            }
        )
    records.sort(key=lambda r: r["job_id"])
    return records


def apply_schedule_to_profile(
    profile: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    horizon: int = DEFAULT_HORIZON,
) -> list[dict[str, float]]:
    """Apply job assignments to baseline profile and return updated hourly load profile.

    Parameters
    ----------
    profile:
        24-hour baseline list with hour/load_mw/grid_stress.
    assignments:
        List of assignment records containing start_hour, duration_hours and power_mw.
    """
    base = _normalize_profile(profile, horizon=horizon)
    out = [{"hour": r["hour"], "load_mw": float(r["load_mw"]), "grid_stress": float(r["grid_stress"])} for r in base]

    for assignment in assignments:
        start = int(assignment["start_hour"])
        duration = int(assignment["duration_hours"])
        power = float(assignment["power_mw"])
        for h in _job_hours(start, duration, horizon=horizon):
            out[h]["load_mw"] += power

    return out


def build_baseline_profile(
    profile: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
    horizon: int = DEFAULT_HORIZON,
) -> list[dict[str, float]]:
    """Build baseline profile using workloads at their current (or default) start times."""
    specs = _normalize_workloads(workloads, horizon=horizon)
    schedule_map = {spec.id: spec.current_start_hour for spec in specs}
    baseline_assignments = _build_assignment_records(specs, schedule_map, horizon=horizon)
    return apply_schedule_to_profile(profile, baseline_assignments, horizon=horizon)


def compute_grid_overlap_score(profile: list[dict[str, Any]]) -> float:
    """Compute weighted load-stress overlap; lower is better."""
    normalized = _normalize_profile(profile)
    return float(sum(float(row["load_mw"]) * float(row["grid_stress"]) for row in normalized))


def compute_peak_load(profile: list[dict[str, Any]]) -> float:
    """Return max hourly load in MW."""
    normalized = _normalize_profile(profile)
    return float(max(float(row["load_mw"]) for row in normalized))


def compute_grid_friendliness_score(profile: list[dict[str, Any]]) -> float:
    """Compute a transparent 0-100 grid-friendliness score.

    Formula:
    - Main term penalizes weighted overlap (load * stress)
    - Small term penalizes high peak-to-mean ratio
    """
    normalized = _normalize_profile(profile)
    loads = np.array([float(r["load_mw"]) for r in normalized], dtype=float)
    stress = np.array([float(r["grid_stress"]) for r in normalized], dtype=float)

    max_stress = float(np.max(stress))
    mean_load = float(np.mean(loads))
    if max_stress <= 1e-9 or mean_load <= 1e-9:
        return 100.0

    overlap_norm = float(np.mean(loads * stress) / (mean_load * max_stress + 1e-9))

    peak_ratio = float(np.max(loads) / (mean_load + 1e-9))
    peak_penalty_norm = np.clip((peak_ratio - 1.0) / 2.0, 0.0, 1.0)

    raw = 100.0 * (1.0 - (0.90 * overlap_norm) - (0.10 * peak_penalty_norm))
    return float(np.clip(raw, 0.0, 100.0))


def _build_summary(schedule_changes: list[dict[str, Any]], profile: list[dict[str, Any]]) -> str:
    """Generate one top-level summary sentence for demo output."""
    shifted = [c for c in schedule_changes if c.get("moved") and c.get("priority") == "flexible"]
    if not shifted:
        return "No flexible jobs were shifted; current schedule already balances constraints and stress reasonably."

    normalized = _normalize_profile(profile)
    high_stress = sorted(normalized, key=lambda r: float(r["grid_stress"]), reverse=True)[:4]
    hours = sorted({int(r["hour"]) for r in high_stress})
    hour_label = ", ".join(str(h) for h in hours)

    return (
        f"{len(shifted)} flexible jobs were shifted away from high-stress hours "
        f"({hour_label}) to reduce grid pressure."
    )


def generate_schedule_changes(
    workloads: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    profile_before: list[dict[str, Any]],
    profile_after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate per-job change records with explanation strings."""
    del profile_after  # reserved for future richer explanations

    stress_by_hour = {
        int(row["hour"]): float(row["grid_stress"])
        for row in _normalize_profile(profile_before)
    }

    assign_by_id = {a["job_id"]: a for a in assignments}
    changes: list[dict[str, Any]] = []

    for raw in workloads:
        job_id = str(raw.get("id"))
        if job_id not in assign_by_id:
            continue

        new_assignment = assign_by_id[job_id]
        priority = str(raw.get("priority", "")).lower()
        duration = int(raw["duration_hours"])

        old_start = int(raw.get("current_start_hour", raw.get("start_hour", raw.get("earliest_start", 0))))
        new_start = int(new_assignment["start_hour"])
        moved = old_start != new_start

        old_hours = _job_hours(old_start, duration)
        new_hours = _job_hours(new_start, duration)
        old_stress = float(np.mean([stress_by_hour[h] for h in old_hours]))
        new_stress = float(np.mean([stress_by_hour[h] for h in new_hours]))

        if priority == "critical":
            reason = "Kept in place because workload is marked critical."
        elif moved and new_stress < old_stress:
            reason = "Moved out of the highest stress window while still finishing before its deadline."
        elif moved and new_start > old_start:
            reason = "Shifted later because the overnight window had lower forecasted grid stress."
        elif moved:
            reason = "Shifted to reduce stress overlap while satisfying duration and finish constraints."
        else:
            reason = "Not moved because no lower-stress feasible slot satisfied duration and finish constraints."

        changes.append(
            {
                "job_id": job_id,
                "job_name": str(raw.get("name", job_id)),
                "priority": priority,
                "old_start_hour": old_start,
                "new_start_hour": new_start,
                "moved": moved,
                "reason": reason,
            }
        )

    changes.sort(key=lambda c: c["job_id"])
    return changes


def _baseline_schedule_map(specs: list[WorkloadSpec]) -> dict[str, int]:
    """Return baseline schedule map from each workload's current start hour."""
    return {spec.id: int(spec.current_start_hour) for spec in specs}


def solve_with_cp_sat(
    profile: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
    horizon: int = DEFAULT_HORIZON,
    anti_bunching_cap_mw: float | None = None,
    max_time_seconds: float = 10.0,
) -> dict[str, Any]:
    """Solve workload scheduling with OR-Tools CP-SAT.

    Returns
    -------
    dict with keys: assignments, status, method
    """
    try:
        from ortools.sat.python import cp_model
    except Exception as exc:  # noqa: BLE001
        raise ImportError("OR-Tools is not available") from exc

    normalized_profile = _normalize_profile(profile, horizon=horizon)
    specs = _normalize_workloads(workloads, horizon=horizon)

    base_load = np.array([float(r["load_mw"]) for r in normalized_profile], dtype=float)
    stress = np.array([float(r["grid_stress"]) for r in normalized_profile], dtype=float)

    base_load_int = np.round(base_load * MW_SCALE).astype(int)
    stress_int = np.round(stress * STRESS_SCALE).astype(int)

    model = cp_model.CpModel()

    x: dict[tuple[str, int], Any] = {}
    for spec in specs:
        for start in spec.candidate_starts:
            x[(spec.id, int(start))] = model.NewBoolVar(f"x_{spec.id}_{start}")

        model.Add(sum(x[(spec.id, s)] for s in spec.candidate_starts) == 1)

        if spec.priority == "critical":
            if spec.current_start_hour not in spec.candidate_starts:
                raise ValueError(
                    f"Critical job {spec.id} current_start_hour={spec.current_start_hour} "
                    "is outside feasible window"
                )
            model.Add(x[(spec.id, spec.current_start_hour)] == 1)

    max_possible_int = int(
        np.max(base_load_int) + sum(int(round(spec.power_mw * MW_SCALE)) for spec in specs)
    )

    total_load_vars = []
    flex_load_vars = []
    bunch_excess_vars = []

    if anti_bunching_cap_mw is None:
        total_flex_power = sum(spec.power_mw for spec in specs if spec.priority == "flexible")
        anti_bunching_cap_mw = max(1.0, 0.50 * total_flex_power)
    flex_cap_int = int(round(anti_bunching_cap_mw * MW_SCALE))

    for h in range(horizon):
        contrib_terms = []
        flex_terms = []

        for spec in specs:
            p_int = int(round(spec.power_mw * MW_SCALE))
            for start in spec.candidate_starts:
                if h in _job_hours(start, spec.duration_hours, horizon=horizon):
                    contrib_terms.append(p_int * x[(spec.id, start)])
                    if spec.priority == "flexible":
                        flex_terms.append(p_int * x[(spec.id, start)])

        hour_load = model.NewIntVar(0, max_possible_int, f"total_load_{h}")
        model.Add(hour_load == int(base_load_int[h]) + sum(contrib_terms))
        total_load_vars.append(hour_load)

        flex_hour = model.NewIntVar(0, max_possible_int, f"flex_load_{h}")
        model.Add(flex_hour == sum(flex_terms))
        flex_load_vars.append(flex_hour)

        # Soft anti-bunching penalty.
        excess = model.NewIntVar(0, max_possible_int, f"bunch_excess_{h}")
        model.Add(excess >= flex_hour - flex_cap_int)
        model.Add(excess >= 0)
        bunch_excess_vars.append(excess)

    peak_load = model.NewIntVar(0, max_possible_int, "peak_load")
    for hour_load in total_load_vars:
        model.Add(peak_load >= hour_load)

    stress_overlap_term = sum(int(stress_int[h]) * total_load_vars[h] for h in range(horizon))

    movement_terms = []
    for spec in specs:
        for start in spec.candidate_starts:
            move_dist = _circular_distance(start, spec.current_start_hour, horizon=horizon)
            p_int = int(round(spec.power_mw * MW_SCALE))
            movement_terms.append(move_dist * p_int * x[(spec.id, start)])

    bunching_term = sum(bunch_excess_vars)

    model.Minimize(
        STRESS_WEIGHT * stress_overlap_term
        + PEAK_WEIGHT * peak_load
        + MOVEMENT_WEIGHT * sum(movement_terms)
        + BUNCHING_WEIGHT * bunching_term
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_time_seconds)
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("CP-SAT did not find a feasible solution")

    schedule_map: dict[str, int] = {}
    for spec in specs:
        selected = [s for s in spec.candidate_starts if solver.Value(x[(spec.id, s)]) == 1]
        if not selected:
            raise RuntimeError(f"No start selected for job {spec.id}")
        schedule_map[spec.id] = int(selected[0])

    assignments = _build_assignment_records(specs, schedule_map, horizon=horizon)

    if status == cp_model.OPTIMAL:
        status_str = "optimal"
    else:
        status_str = "feasible"

    return {
        "assignments": assignments,
        "status": status_str,
        "method": "cp_sat",
        "objective_value": float(solver.ObjectiveValue()),
    }


def solve_with_greedy(
    profile: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
    horizon: int = DEFAULT_HORIZON,
    anti_bunching_cap_mw: float | None = None,
) -> dict[str, Any]:
    """Solve workload scheduling with a robust greedy heuristic fallback."""
    normalized_profile = _normalize_profile(profile, horizon=horizon)
    specs = _normalize_workloads(workloads, horizon=horizon)

    base_load = np.array([float(r["load_mw"]) for r in normalized_profile], dtype=float)
    stress = np.array([float(r["grid_stress"]) for r in normalized_profile], dtype=float)

    if anti_bunching_cap_mw is None:
        total_flex_power = sum(spec.power_mw for spec in specs if spec.priority == "flexible")
        anti_bunching_cap_mw = max(1.0, 0.50 * total_flex_power)

    schedule_map: dict[str, int] = {}

    # Keep critical jobs fixed first.
    running_load = base_load.copy()
    flex_added = np.zeros(horizon, dtype=float)

    critical = [s for s in specs if s.priority == "critical"]
    flexible = [s for s in specs if s.priority == "flexible"]

    for spec in critical:
        schedule_map[spec.id] = spec.current_start_hour
        for h in _job_hours(spec.current_start_hour, spec.duration_hours, horizon=horizon):
            running_load[h] += spec.power_mw

    # High-impact first for better greedy quality.
    flexible_sorted = sorted(
        flexible,
        key=lambda s: s.power_mw * s.duration_hours,
        reverse=True,
    )

    for spec in flexible_sorted:
        best_start = spec.current_start_hour
        best_score = float("inf")

        for candidate in spec.candidate_starts:
            candidate_load = running_load.copy()
            candidate_flex = flex_added.copy()

            for h in _job_hours(candidate, spec.duration_hours, horizon=horizon):
                candidate_load[h] += spec.power_mw
                candidate_flex[h] += spec.power_mw

            stress_term = float(np.sum(candidate_load * stress))
            peak_term = float(np.max(candidate_load))
            move_term = float(_circular_distance(candidate, spec.current_start_hour, horizon=horizon) * spec.power_mw)
            bunch_term = float(np.sum(np.maximum(0.0, candidate_flex - anti_bunching_cap_mw)))

            score = (
                STRESS_WEIGHT * stress_term
                + PEAK_WEIGHT * peak_term
                + MOVEMENT_WEIGHT * move_term
                + BUNCHING_WEIGHT * bunch_term
            )

            if score < best_score:
                best_score = score
                best_start = int(candidate)

        schedule_map[spec.id] = best_start
        for h in _job_hours(best_start, spec.duration_hours, horizon=horizon):
            running_load[h] += spec.power_mw
            flex_added[h] += spec.power_mw

    assignments = _build_assignment_records(specs, schedule_map, horizon=horizon)
    return {
        "assignments": assignments,
        "status": "feasible",
        "method": "greedy",
        "objective_value": None,
    }


def optimize_schedule(
    profile: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
    method: str = "cp_sat",
    horizon: int = DEFAULT_HORIZON,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Optimize workload schedule and return backend-ready result payload."""
    normalized_profile = _normalize_profile(profile, horizon=horizon)

    baseline_profile = build_baseline_profile(normalized_profile, workloads, horizon=horizon)

    if method not in {"cp_sat", "greedy"}:
        raise ValueError("method must be 'cp_sat' or 'greedy'")

    solver_result: dict[str, Any]
    if method == "cp_sat":
        try:
            solver_result = solve_with_cp_sat(normalized_profile, workloads, horizon=horizon)
        except Exception as exc:  # noqa: BLE001
            if logger is not None:
                logger.warning("CP-SAT unavailable/failed (%s). Falling back to greedy solver.", exc)
            solver_result = solve_with_greedy(normalized_profile, workloads, horizon=horizon)
            solver_result["fallback_reason"] = str(exc)
    else:
        solver_result = solve_with_greedy(normalized_profile, workloads, horizon=horizon)

    assignments = solver_result["assignments"]
    optimized_profile = apply_schedule_to_profile(normalized_profile, assignments, horizon=horizon)

    schedule_changes = generate_schedule_changes(
        workloads=workloads,
        assignments=assignments,
        profile_before=baseline_profile,
        profile_after=optimized_profile,
    )

    overlap_before = compute_grid_overlap_score(baseline_profile)
    overlap_after = compute_grid_overlap_score(optimized_profile)
    peak_before = compute_peak_load(baseline_profile)
    peak_after = compute_peak_load(optimized_profile)

    if overlap_before <= 1e-9:
        overlap_reduction = 0.0
    else:
        overlap_reduction = ((overlap_before - overlap_after) / overlap_before) * 100.0

    jobs_shifted = sum(
        1
        for c in schedule_changes
        if c["priority"] == "flexible" and c["moved"]
    )

    metrics = {
        "peak_overlap_reduction": round(float(overlap_reduction), 2),
        "jobs_shifted": int(jobs_shifted),
        "grid_friendliness_score_before": round(compute_grid_friendliness_score(baseline_profile), 2),
        "grid_friendliness_score_after": round(compute_grid_friendliness_score(optimized_profile), 2),
        "peak_load_before": round(float(peak_before), 2),
        "peak_load_after": round(float(peak_after), 2),
    }

    summary = _build_summary(schedule_changes, normalized_profile)

    return {
        "baseline_profile": baseline_profile,
        "optimized_profile": optimized_profile,
        "schedule_changes": schedule_changes,
        "job_assignments": assignments,
        "metrics": metrics,
        "summary": summary,
        "solver": {
            "method": solver_result.get("method", method),
            "status": solver_result.get("status", "unknown"),
            "objective_value": solver_result.get("objective_value"),
            "fallback_reason": solver_result.get("fallback_reason"),
        },
    }


class OptimizationService:
    """Backend wrapper exposing optimize() for Flask routes."""

    def __init__(self, logger: logging.Logger, explanation_service: Any | None = None):
        self.logger = logger
        self.explanation_service = explanation_service

    def optimize(self, profile: list[dict[str, Any]], workloads: list[dict[str, Any]]) -> dict[str, Any]:
        """Route-facing optimization entrypoint (defaults to CP-SAT with fallback)."""
        return optimize_schedule(
            profile=profile,
            workloads=workloads,
            method="cp_sat",
            logger=self.logger,
        )


if __name__ == "__main__":
    sample_profile = [
        {"hour": h, "load_mw": 11.0 + 0.15 * np.sin(h / 24 * 2 * np.pi), "grid_stress": 0.2 + 0.7 * max(0.0, np.sin((h - 12) / 24 * 2 * np.pi))}
        for h in range(24)
    ]

    sample_workloads = [
        {
            "id": "job_1",
            "name": "AI Batch Training",
            "duration_hours": 3,
            "earliest_start": 18,
            "latest_finish": 24,
            "priority": "flexible",
            "power_mw": 2.5,
            "current_start_hour": 18,
        },
        {
            "id": "job_2",
            "name": "Nightly Backup",
            "duration_hours": 2,
            "earliest_start": 20,
            "latest_finish": 8,
            "priority": "flexible",
            "power_mw": 1.3,
            "current_start_hour": 20,
        },
        {
            "id": "job_3",
            "name": "Core Serving",
            "duration_hours": 24,
            "earliest_start": 0,
            "latest_finish": 24,
            "priority": "critical",
            "power_mw": 6.0,
            "current_start_hour": 0,
        },
    ]

    result = optimize_schedule(sample_profile, sample_workloads, method="cp_sat")
    print("Solver:", result["solver"])
    print("Metrics:", result["metrics"])
    print("Summary:", result["summary"])
