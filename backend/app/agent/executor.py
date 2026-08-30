from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.models.schemas import (
    EnvParamsJobSpec,
    ExecutorCallRecord,
    ExecutorResult,
    HeatmapJobSpec,
    TaskPlan,
)
from app.tools.fortyguard_client import (
    FortyGuardClient,
    FortyGuardError,
    is_retryable_http,
)
from app.tools.geo import validate_plan

logger = logging.getLogger(__name__)

SubmitFn = Callable[..., Awaitable[str]]


class Executor:
    def __init__(self, client: FortyGuardClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def execute(self, plan: TaskPlan) -> ExecutorResult:
        errors = validate_plan(plan, self.settings.fortyguard_max_aoi_mi2)
        if errors:
            return ExecutorResult(calls=[], validation_errors=errors)

        calls: list[ExecutorCallRecord] = []
        usage: dict[str, Any] | None = None

        try:
            usage_payload = await self.client.fetch_api_key_usage()
            usage = usage_payload
            calls.append(
                ExecutorCallRecord(
                    label="credits",
                    endpoint="/v1/system/fetch-api-key-usage",
                    status="succeeded",
                    result=_as_dict(usage_payload),
                )
            )
        except FortyGuardError as exc:
            logger.warning("credit check failed (continuing): %s", exc)
            calls.append(
                ExecutorCallRecord(
                    label="credits",
                    endpoint="/v1/system/fetch-api-key-usage",
                    status="skipped",
                    error=str(exc),
                )
            )

        for job in plan.heatmap_jobs:
            calls.append(await self._run_heatmap(job))
        for job in plan.env_params_jobs:
            calls.append(await self._run_env_params(job))
        return ExecutorResult(calls=calls, usage=usage)

    async def _run_heatmap(self, job: HeatmapJobSpec) -> ExecutorCallRecord:
        return await self._submit_and_wait(
            label=job.label,
            endpoint=job.endpoint,
            submit=lambda: self.client.create_heatmap(
                polygon_aoi=job.polygon_aoi,
                date_time=job.date_time,
                granularity=job.granularity,
                analytic_type=job.analytic_type,
                threshold=job.threshold,
                direction=job.direction,
                label=job.label,
            ),
        )

    async def _run_env_params(self, job: EnvParamsJobSpec) -> ExecutorCallRecord:
        return await self._submit_and_wait(
            label=job.label,
            endpoint=job.endpoint,
            submit=lambda: self.client.environmental_parameters(
                latitude=job.latitude,
                longitude=job.longitude,
                temperature=job.temperature,
                date_time=job.date_time,
                analysis=job.analysis,
                label=job.label,
            ),
        )

    async def _submit_and_wait(
        self,
        *,
        label: str,
        endpoint: str,
        submit: SubmitFn,
    ) -> ExecutorCallRecord:
        attempts = 0
        last_error: str | None = None
        delay = self.settings.aegis_initial_poll_delay_seconds

        while attempts < self.settings.aegis_max_retries:
            attempts += 1
            try:
                activity_id = await submit()
                payload = await self.client.wait_for_result(
                    activity_id,
                    timeout_seconds=self.settings.aegis_poll_timeout_seconds,
                    initial_delay=self.settings.aegis_initial_poll_delay_seconds,
                    max_delay=self.settings.aegis_max_poll_delay_seconds,
                )
                result = _result_of(payload)
                return ExecutorCallRecord(
                    label=label,
                    endpoint=endpoint,
                    activity_id=activity_id,
                    status="succeeded",
                    attempts=attempts,
                    result=result,
                )
            except FortyGuardError as exc:
                last_error = str(exc)
                if not is_retryable_http(exc) or attempts >= self.settings.aegis_max_retries:
                    return ExecutorCallRecord(
                        label=label,
                        endpoint=endpoint,
                        status="failed",
                        attempts=attempts,
                        error=last_error,
                    )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.settings.aegis_max_poll_delay_seconds)

        return ExecutorCallRecord(
            label=label,
            endpoint=endpoint,
            status="failed",
            attempts=attempts,
            error=last_error or "exhausted retries",
        )


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {"value": payload}


def _result_of(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    result = data.get("result")
    if isinstance(result, dict):
        return result
    return _as_dict(payload)
