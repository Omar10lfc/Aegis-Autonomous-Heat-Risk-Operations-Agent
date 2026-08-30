"""Eval harness (mocked FortyGuard, heuristic planner). Expand to 10–15 later."""

from __future__ import annotations

import pytest

from app.agent.graph import run_pipeline
from app.config import Settings
from app.models.schemas import AnalysisLayer


CASES = [
    {
        "id": "logistics_exceedance",
        "brief": "Which of our Phoenix distribution routes crossed 35C thresholds last month, and where should we reroute?",
        "layer": AnalysisLayer.EXCEEDANCE,
        "endpoints": {"/v1/heatmap", "/v1/env_params"},
    },
    {
        "id": "logistics_snapshot",
        "brief": "Give me a 3pm snapshot of heat at the Phoenix Sky Harbor yard on 15 July 2024.",
        "layer": AnalysisLayer.SNAPSHOT,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "logistics_persistence",
        "brief": "Where did sustained heat persist the longest across our Phoenix yards yesterday afternoon?",
        "layer": AnalysisLayer.PERSISTENCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "insurance_exceedance",
        "brief": "For underwriting, which Phoenix yards exceeded dangerous heat thresholds last month?",
        "layer": AnalysisLayer.EXCEEDANCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "insurance_snapshot",
        "brief": "Insurance inspection: snapshot heat at our Tempe cross-dock on 15 July 2024 at 15:00.",
        "layer": AnalysisLayer.SNAPSHOT,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "real_estate_persistence",
        "brief": "Did any Phoenix warehouse pocket see consecutive hours of persistent extreme heat last month?",
        "layer": AnalysisLayer.PERSISTENCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "logistics_reroute_exceedance",
        "brief": "Our Phoenix delivery routes need rerouting where afternoon temps crossed dangerous levels yesterday.",
        "layer": AnalysisLayer.EXCEEDANCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "logistics_snapshot_single_site",
        "brief": "Snapshot the 3pm ambient temperature at the Tempe cross-dock on 15 July 2024.",
        "layer": AnalysisLayer.SNAPSHOT,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "insurance_persistence_underwriting",
        "brief": "For underwriting renewal, how long did sustained heat persist near our insured Phoenix depots last month?",
        "layer": AnalysisLayer.PERSISTENCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "insurance_threshold_claim_review",
        "brief": "A claim says our Mesa yard exceeded 40C for hours — verify which days crossed that threshold last month.",
        "layer": AnalysisLayer.EXCEEDANCE,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "real_estate_snapshot_due_diligence",
        "brief": "Due diligence snapshot of street-level heat around the Phoenix Sky Harbor parcel at 15:00 on 2024-07-15.",
        "layer": AnalysisLayer.SNAPSHOT,
        "endpoints": {"/v1/heatmap"},
    },
    {
        "id": "logistics_longest_run_persistence",
        "brief": "Which Phoenix yard had the longest run of extreme heat hours on end last month?",
        "layer": AnalysisLayer.PERSISTENCE,
        "endpoints": {"/v1/heatmap"},
    },
]


def _settings() -> Settings:
    return Settings(
        fortyguard_live=False,
        fortyguard_api_key="unused",
        openrouter_api_key="",
        aegis_llm_mode="heuristic",
        langchain_tracing_v2=False,
        langchain_api_key="",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_eval_case(case: dict):
    result = await run_pipeline(case["brief"], settings=_settings())
    plan = result["plan"]
    assert plan["analysis_layer"] == case["layer"].value
    endpoints = {job["endpoint"] for job in plan["heatmap_jobs"]} | {
        job["endpoint"] for job in plan["env_params_jobs"]
    }
    assert case["endpoints"].issubset(endpoints)
    assert result["citations"], "report must cite returned data points"
    assert any(c.get("activity_id") and c.get("value") is not None for c in result["citations"])
    assert result.get("markdown")
