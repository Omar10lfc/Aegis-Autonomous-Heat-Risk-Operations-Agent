"""Cached FortyGuard payloads so the pipeline runs without live credit spend.

Per-site variation is derived deterministically from the site label so demo
rankings are stable, meaningful, and reproducible across runs.
"""

from __future__ import annotations

import hashlib
from typing import Any


def _site_offsets(seed: str, spread: float, n: int = 2) -> list[float]:
    digest = hashlib.sha256(seed.encode()).digest()
    return [((int.from_bytes(digest[i * 4 : i * 4 + 4], "big") / 0xFFFFFFFF) - 0.5) * 2 * spread for i in range(n)]


def cached_usage() -> dict[str, Any]:
    return {
        "error": False,
        "status_code": 200,
        "message": "cached",
        "data": {
            "plan": "Hackathon",
            "credits_remaining": 2_000_000,
            "mode": "cached",
        },
    }


def cached_heatmap_result(*, analytic_type: str, threshold: float | None, label: str) -> dict[str, Any]:
    off_max, off_min = _site_offsets(f"heatmap:{label}", 3.0 if analytic_type != "persistence" else 2.5)
    if analytic_type == "exceedance":
        hot = round(11 + off_max, 1)
        stats = {
            "analytic_type": "exceedance",
            "units": "hour",
            "n_cells": 36,
            "min": max(0.0, round(hot - (5.0 + off_min), 1)),
            "max": hot,
            "mean": round(hot * 0.58, 1),
            "threshold_celsius": threshold or 35.0,
        }
        value_key = "value"
    elif analytic_type == "persistence":
        hot = round(7 + off_max, 1)
        stats = {
            "analytic_type": "persistence",
            "units": "hour",
            "n_cells": 36,
            "min": max(0.0, round(hot - (4.0 + off_min), 1)),
            "max": hot,
            "mean": round(hot * 0.45, 1),
            "threshold_celsius": threshold or 35.0,
        }
        value_key = "value"
    else:
        hot = round(44.8 + off_max, 1)
        low = round(hot - (8.6 + abs(off_min)), 1)
        stats = {
            "analytic_type": "tcm",
            "units": "celsius",
            "Temperature_stats": {
                "Minimum": low,
                "Maximum": hot,
                "Mean": round((hot + low) / 2, 1),
                "Standard_deviation": 1.8,
            },
        }
        value_key = "temperature"

    lon, lat = -112.065, 33.44
    feature = {
        "type": "Feature",
        "properties": {
            "site_label": label,
            value_key: hot,
            "analytic_type": analytic_type,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon, lat],
                    [lon + 0.001, lat],
                    [lon + 0.001, lat + 0.001],
                    [lon, lat + 0.001],
                    [lon, lat],
                ]
            ],
        },
    }
    return {
        "map_data": {"type": "FeatureCollection", "features": [feature]},
        "stats_data": stats,
    }


def cached_env_params_result(*, latitude: float, longitude: float, temperature: float) -> dict[str, Any]:
    off_hi, _off_wb = _site_offsets(f"env:{latitude},{longitude}", 3.0)
    return {
        "metadata": {
            "timezone": "America/Phoenix",
            "timezone_offset_hours": -7,
            "timestamps": ["2024-07-15T14:00:00-07:00"],
        },
        "locations": [
            {
                "lat": latitude,
                "lon": longitude,
                "elevation": 331,
                "temperature": temperature,
                "parameters": {
                    "heat_index_celsius": [round(46.2 + off_hi, 1)],
                    "wet_bulb_temperature_celsius": [24.1],
                    "air_quality:idx": [62],
                },
            }
        ],
    }
