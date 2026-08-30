"""Analyzer: snapshot / exceedance / persistence over executor results."""

from __future__ import annotations

from typing import Any

from langsmith import traceable

from app.models.schemas import AnalysisLayer, ExecutorCallRecord, ExecutorResult, TaskPlan
from app.tools.redact import redact_mapping

# What the ranking number means per FortyGuard analytic_type.
METRIC_LABELS = {
    "tcm": "peak_temp_celsius",
    "time_of_measure": "peak_temp_celsius",
    "exceedance": "hours_above_threshold",
    "persistence": "longest_sustained_hours",
}


def _stats(call: ExecutorCallRecord) -> dict[str, Any]:
    result = call.result or {}
    stats = result.get("stats_data") or {}
    temp = stats.get("Temperature_stats") or {}
    analytic = stats.get("analytic_type")
    return {
        "label": call.label,
        "activity_id": call.activity_id,
        "endpoint": call.endpoint,
        "metric": METRIC_LABELS.get(str(analytic), "value"),
        "min": stats.get("min") if "min" in stats else temp.get("Minimum"),
        "max": stats.get("max") if "max" in stats else temp.get("Maximum"),
        "mean": stats.get("mean") if "mean" in stats else temp.get("Mean"),
        "units": stats.get("units") or ("celsius" if temp else None),
        "analytic_type": analytic,
        "n_cells": stats.get("n_cells"),
        "heat_index_celsius": _heat_index(result),
    }


def _heat_index(result: dict[str, Any]) -> float | None:
    locations = result.get("locations") or []
    if not locations:
        return None
    params = locations[0].get("parameters") or {}
    series = params.get("heat_index_celsius") or []
    return series[0] if series else None


@traceable(name="analyzer", process_inputs=redact_mapping, process_outputs=redact_mapping)
def analyze(plan: TaskPlan, executor_result: ExecutorResult) -> dict[str, Any]:
    heatmaps = [c for c in executor_result.calls if c.endpoint == "/v1/heatmap" and c.status == "succeeded"]
    envs = [c for c in executor_result.calls if c.endpoint == "/v1/env_params" and c.status == "succeeded"]
    rows = [_stats(c) for c in heatmaps]
    rows.sort(key=lambda r: (r.get("max") is None, -(r.get("max") or 0)))

    citations: list[dict[str, Any]] = []
    for row in rows:
        citations.append(
            {
                "endpoint": row["endpoint"],
                "activity_id": row["activity_id"],
                "label": row["label"],
                "field": row["metric"],
                "value": row["max"],
                "units": row["units"],
            }
        )
    for call in envs:
        hi = _heat_index(call.result or {})
        citations.append(
            {
                "endpoint": call.endpoint,
                "activity_id": call.activity_id,
                "label": call.label,
                "field": "heat_index_celsius",
                "value": hi,
                "units": "celsius",
            }
        )

    hottest = rows[0] if rows else None
    return {
        "layer": plan.analysis_layer.value,
        "threshold_celsius": plan.heat_threshold_celsius,
        "ranked_sites": rows,
        "hottest": hottest,
        "env_points": [_stats(c) for c in envs],
        "citations": citations,
        "validation_errors": executor_result.validation_errors,
        "failed_calls": [
            {"label": c.label, "error": c.error} for c in executor_result.calls if c.status == "failed"
        ],
    }
