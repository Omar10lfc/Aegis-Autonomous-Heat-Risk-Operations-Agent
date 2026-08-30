from __future__ import annotations

from typing import Any

import pytest

from app.agent.executor import Executor
from app.config import Settings
from app.models.schemas import (
    AnalysisLayer,
    DateTimeSpec,
    EnvParamsJobSpec,
    HeatmapJobSpec,
    TaskPlan,
)
from app.tools.fortyguard_client import FortyGuardError, FortyGuardTimeout
from tests.fixtures.geo import DUBAI_AOI, PHOENIX_WAREHOUSE_AOI


def _settings(**overrides: Any) -> Settings:
    values = {
        "fortyguard_api_key": "test-key",
        "fortyguard_max_aoi_mi2": 10.0,
        "aegis_poll_timeout_seconds": 20.0,
        "aegis_max_retries": 3,
        "aegis_initial_poll_delay_seconds": 0.01,
        "aegis_max_poll_delay_seconds": 0.05,
    }
    values.update(overrides)
    return Settings(**values)


class FakeClient:
    def __init__(self) -> None:
        self.heatmap_submits = 0
        self.env_submits = 0
        self.status_polls = 0
        self.usage_calls = 0
        self.heatmap_queue: list[Any] = ["act-heatmap-1"]
        self.env_queue: list[Any] = ["act-env-1"]
        self.status_by_id: dict[str, list[dict[str, Any]]] = {}
        self.usage_payload: dict[str, Any] | Exception = {
            "data": {"credits_remaining": 999_000}
        }

    async def fetch_api_key_usage(self) -> dict[str, Any]:
        self.usage_calls += 1
        if isinstance(self.usage_payload, Exception):
            raise self.usage_payload
        return self.usage_payload

    async def create_heatmap(self, **_: Any) -> str:
        self.heatmap_submits += 1
        item = self.heatmap_queue.pop(0) if self.heatmap_queue else "act-heatmap-1"
        if isinstance(item, Exception):
            raise item
        return str(item)

    async def environmental_parameters(self, **_: Any) -> str:
        self.env_submits += 1
        item = self.env_queue.pop(0) if self.env_queue else "act-env-1"
        if isinstance(item, Exception):
            raise item
        return str(item)

    async def wait_for_result(self, activity_id: str, **_: Any) -> dict[str, Any]:
        self.status_polls += 1
        queue = self.status_by_id.setdefault(
            activity_id,
            [
                {
                    "data": {
                        "activity_id": activity_id,
                        "status": "Completed",
                        "result": {"map_data": {"type": "FeatureCollection", "features": []}},
                    }
                }
            ],
        )
        item = queue.pop(0) if queue else queue
        if isinstance(item, Exception):
            raise item
        return item


def phoenix_plan() -> TaskPlan:
    dt = DateTimeSpec(start_date="2024-07-15", start_time="14:00", filter_type=1)
    return TaskPlan(
        brief="Which Phoenix warehouse pocket crossed 35C last July afternoon?",
        analysis_layer=AnalysisLayer.EXCEEDANCE,
        rationale="threshold language + named Phoenix AOI",
        heatmap_jobs=[
            HeatmapJobSpec(
                polygon_aoi=PHOENIX_WAREHOUSE_AOI,
                date_time=dt,
                granularity=100,
                analytic_type="exceedance",
                threshold=35.0,
                direction="above",
                label="phx-warehouse",
            )
        ],
        env_params_jobs=[
            EnvParamsJobSpec(
                latitude=33.44,
                longitude=-112.065,
                temperature=41.0,
                date_time=dt,
                analysis=["heat_index_celsius", "wet_bulb_temperature_celsius", "air_quality:idx"],
                label="phx-env",
            )
        ],
        heat_threshold_celsius=35.0,
        client_framing="logistics",
    )


@pytest.mark.asyncio
async def test_executor_happy_path_heatmap_and_env_params():
    client = FakeClient()
    executor = Executor(client, _settings())  # type: ignore[arg-type]
    result = await executor.execute(phoenix_plan())

    assert result.validation_errors == []
    assert client.heatmap_submits == 1
    assert client.env_submits == 1
    assert client.usage_calls == 1
    statuses = {call.label: call.status for call in result.calls}
    assert statuses["phx-warehouse"] == "succeeded"
    assert statuses["phx-env"] == "succeeded"
    warehouse = next(c for c in result.calls if c.label == "phx-warehouse")
    assert warehouse.activity_id == "act-heatmap-1"
    assert warehouse.result is not None
    assert "map_data" in warehouse.result


@pytest.mark.asyncio
async def test_executor_rejects_non_us_aoi_before_submit():
    plan = phoenix_plan()
    plan.heatmap_jobs[0].polygon_aoi = DUBAI_AOI
    plan.env_params_jobs = []
    client = FakeClient()
    executor = Executor(client, _settings())  # type: ignore[arg-type]
    result = await executor.execute(plan)

    assert result.validation_errors
    assert any("U.S." in msg for msg in result.validation_errors)
    assert client.heatmap_submits == 0
    assert client.usage_calls == 0


@pytest.mark.asyncio
async def test_executor_retries_transient_submit_then_succeeds():
    client = FakeClient()
    client.heatmap_queue = [
        FortyGuardError("HTTP 429 from /v1/heatmap: rate limited"),
        "act-heatmap-retry",
    ]
    plan = phoenix_plan()
    plan.env_params_jobs = []
    executor = Executor(client, _settings())  # type: ignore[arg-type]
    result = await executor.execute(plan)

    warehouse = next(c for c in result.calls if c.label == "phx-warehouse")
    assert warehouse.status == "succeeded"
    assert warehouse.attempts == 2
    assert client.heatmap_submits == 2


@pytest.mark.asyncio
async def test_executor_stops_after_max_retries():
    client = FakeClient()
    client.heatmap_queue = [
        FortyGuardError("HTTP 503 from /v1/heatmap: upstream"),
        FortyGuardError("HTTP 503 from /v1/heatmap: upstream"),
        FortyGuardError("HTTP 503 from /v1/heatmap: upstream"),
    ]
    plan = phoenix_plan()
    plan.env_params_jobs = []
    executor = Executor(client, _settings(aegis_max_retries=3))  # type: ignore[arg-type]
    result = await executor.execute(plan)

    warehouse = next(c for c in result.calls if c.label == "phx-warehouse")
    assert warehouse.status == "failed"
    assert warehouse.attempts == 3
    assert "503" in (warehouse.error or "")


@pytest.mark.asyncio
async def test_executor_surfaces_poll_timeout():
    client = FakeClient()
    client.status_by_id["act-heatmap-1"] = [
        FortyGuardTimeout("FortyGuard task act-heatmap-1 did not finish within 20s (last status=processing).")
    ]
    plan = phoenix_plan()
    plan.env_params_jobs = []
    executor = Executor(client, _settings())  # type: ignore[arg-type]
    result = await executor.execute(plan)

    warehouse = next(c for c in result.calls if c.label == "phx-warehouse")
    assert warehouse.status == "failed"
    assert "did not finish" in (warehouse.error or "")


@pytest.mark.asyncio
async def test_wait_for_result_backoff_and_timeout():
    from app.tools.fortyguard_client import FortyGuardClient

    sleeps: list[float] = []
    client = FortyGuardClient(_settings(), http=None)
    polls = {"n": 0}

    async def get_status(activity_id: str) -> dict[str, Any]:
        polls["n"] += 1
        return {"data": {"activity_id": activity_id, "status": "Processing"}}

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client.get_status = get_status  # type: ignore[method-assign]
    with pytest.raises(FortyGuardTimeout):
        await client.wait_for_result(
            "abc",
            timeout_seconds=10,
            initial_delay=3,
            max_delay=12,
            sleeper=fake_sleep,
        )

    assert sleeps[:3] == [3, 6, 12]
    assert polls["n"] >= 3


@pytest.mark.asyncio
async def test_wait_for_result_failed_status_does_not_hang():
    from app.tools.fortyguard_client import FortyGuardClient

    client = FortyGuardClient(_settings(), http=None)

    async def get_status(activity_id: str) -> dict[str, Any]:
        return {"data": {"activity_id": activity_id, "status": "Failed"}}

    async def no_sleep(_: float) -> None:
        return None

    client.get_status = get_status  # type: ignore[method-assign]
    with pytest.raises(FortyGuardError, match="failed"):
        await client.wait_for_result("abc", timeout_seconds=30, sleeper=no_sleep)
