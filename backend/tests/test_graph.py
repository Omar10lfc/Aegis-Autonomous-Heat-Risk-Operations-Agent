import pytest

# pyrefly: ignore [missing-import]
from app.agent.graph import run_pipeline
from app.agent.planner import heuristic_plan, infer_layer
from app.config import Settings
from app.models.schemas import AnalysisLayer
from app.tools.geo import validate_heatmap
from app.models.schemas import DateTimeSpec, HeatmapJobSpec
from tests.fixtures.geo import PHOENIX_WAREHOUSE_AOI


def _settings() -> Settings:
    return Settings(
        fortyguard_live=False,
        fortyguard_api_key="unused",
        openrouter_api_key="",
        aegis_llm_mode="heuristic",
        langchain_tracing_v2=False,
        langchain_api_key="",
    )


def test_planner_maps_threshold_brief_to_exceedance():
    plan = heuristic_plan(
        "Which of our Phoenix distribution routes crossed dangerous heat thresholds last month, and where should we reroute?"
    )
    assert plan.analysis_layer == AnalysisLayer.EXCEEDANCE
    assert plan.heatmap_jobs
    assert all(job.endpoint == "/v1/heatmap" for job in plan.heatmap_jobs)
    assert all(job.analytic_type == "exceedance" for job in plan.heatmap_jobs)
    assert all(job.date_time.filter_type in {1, 2, 3} for job in plan.heatmap_jobs)
    assert plan.env_params_jobs
    assert all(job.endpoint == "/v1/env_params" for job in plan.env_params_jobs)


def test_infer_persistence():
    assert infer_layer("How long did sustained heat persist at the Tempe yard?") == AnalysisLayer.PERSISTENCE


def test_filter_type_4_rejected_before_submit():
    job = HeatmapJobSpec(
        polygon_aoi=PHOENIX_WAREHOUSE_AOI,
        date_time=DateTimeSpec(start_date="2024-07-01", end_date="2024-07-31", filter_type=4),
        granularity=100,
    )
    errors = validate_heatmap(job, max_aoi_mi2=10)
    assert any("1–3" in msg or "1-3" in msg for msg in errors)


@pytest.mark.asyncio
async def test_cached_pipeline_emits_citations():
    result = await run_pipeline(
        "Snapshot the 3pm heat at our Phoenix Sky Harbor yard on 15 July 2024.",
        settings=_settings(),
    )
    assert result.get("markdown")
    assert result.get("citations")
    assert any(c.get("activity_id") for c in result["citations"])
    assert any(c.get("endpoint") == "/v1/heatmap" for c in result["citations"])
    assert result.get("fortyguard_mode") == "cached"


def test_forecast_plan_omits_env_params():
    from datetime import timedelta
    from app.agent.planner import PlannerDraft, draft_to_plan
    from app.models.schemas import utc_now

    future = utc_now() + timedelta(hours=2)
    draft = PlannerDraft(
        analysis_layer=AnalysisLayer.EXCEEDANCE,
        client_framing="logistics",
        heat_threshold_celsius=35.0,
        filter_type=1,
        start_date=future.strftime("%Y-%m-%d"),
        start_time=future.strftime("%H:%M"),
        site_ids=["phx_sky_harbor_yard"],
        include_env_params=True,
        rationale="testing forecast plan",
    )
    plan = draft_to_plan("test forecast", draft)
    assert len(plan.heatmap_jobs) == 1
    assert len(plan.env_params_jobs) == 0


def test_template_memo_suppresses_empty_ranked_sites_on_validation():
    from app.agent.planner import heuristic_plan
    from app.agent.synthesizer import template_memo

    plan = heuristic_plan("Test brief")
    analysis = {
        "layer": "exceedance",
        "ranked_sites": [],
        "validation_errors": ["start date/time is beyond horizon."],
    }
    memo = template_memo(plan, analysis, "heuristic")
    assert "## Ranked Sites" not in memo
    assert "## Validation" in memo
    assert "start date/time is beyond horizon." in memo

