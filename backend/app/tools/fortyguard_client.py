"""Thin wrapper around the official Temperature API Quickstart `fortyguard` package.

Live calls are opt-in (`FORTYGUARD_LIVE=true`). Default is cached payloads so
the LangGraph pipeline never spends credits until Omar authorizes it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models.schemas import TERMINAL_FAILURE, TERMINAL_SUCCESS, DateTimeSpec
from app.tools.cache import cached_env_params_result, cached_heatmap_result, cached_usage
from app.tools.redact import redact_value

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_VENDOR = Path(__file__).resolve().parents[3] / "vendor" / "temperature-api-quickstart"
if _VENDOR.exists() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


class FortyGuardError(RuntimeError):
    pass


class FortyGuardTimeout(FortyGuardError):
    pass


def _try_official_client(api_key: str, base_url: str) -> Any | None:
    try:
        from fortyguard import FortyGuardClient as Upstream
    except ImportError:
        logger.warning("Official fortyguard package not importable; live mode will use HTTP.")
        return None
    return Upstream(api_key=api_key, base_url=base_url, timeout=60.0)


class FortyGuardClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http
        self._owns_http = http is None
        self._live = settings.fortyguard_live
        self._cached_results: dict[str, dict[str, Any]] = {"heatmap": {}, "env": {}}
        self._upstream = None
        if self._live and settings.fortyguard_api_key:
            self._upstream = _try_official_client(
                settings.fortyguard_api_key, settings.fortyguard_base_url.rstrip("/")
            )

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def create_heatmap(
        self,
        *,
        polygon_aoi: dict[str, Any],
        date_time: DateTimeSpec,
        granularity: int = 100,
        analytic_type: str = "tcm",
        threshold: float | None = None,
        direction: str | None = None,
        label: str = "heatmap",
    ) -> str:
        if not self._live:
            activity_id = f"cached-heatmap-{label}-{uuid.uuid4().hex[:8]}"
            self._cached_results["heatmap"][activity_id] = cached_heatmap_result(
                analytic_type=analytic_type, threshold=threshold, label=label
            )
            return activity_id

        if self._upstream is not None:
            activity_id = await asyncio.to_thread(
                self._upstream.create_heatmap,
                polygon_aoi,
                date_time.start_date,
                date_time.filter_type,
                granularity,
                date_time.start_time,
                date_time.end_time,
                date_time.end_date,
                analytic_type,
                threshold,
                direction,
                wait=False,
                verbose=False,
            )
            return str(activity_id)

        body = {
            "polygon_aoi": polygon_aoi,
            "date_time": _date_time_payload(date_time),
            "granularity": granularity,
            "analytic_type": analytic_type,
        }
        if threshold is not None:
            body["threshold"] = threshold
        if direction is not None:
            body["direction"] = direction
        data = await self._post("/v1/heatmap", body)
        return _extract_activity_id(data)

    async def environmental_parameters(
        self,
        *,
        latitude: float,
        longitude: float,
        temperature: float,
        date_time: DateTimeSpec,
        analysis: list[str] | None = None,
        label: str = "env_params",
    ) -> str:
        if not self._live:
            activity_id = f"cached-env-{label}-{uuid.uuid4().hex[:8]}"
            self._cached_results["env"][activity_id] = cached_env_params_result(
                latitude=latitude, longitude=longitude, temperature=temperature
            )
            return activity_id

        if self._upstream is not None:
            activity_id = await asyncio.to_thread(
                self._upstream.environmental_parameters,
                latitude,
                longitude,
                temperature,
                date_time.start_date,
                date_time.filter_type,
                date_time.start_time,
                date_time.end_time,
                date_time.end_date,
                analysis,
                wait=False,
                verbose=False,
            )
            return str(activity_id)

        body: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temperature,
            "date_time": _date_time_payload(date_time),
        }
        if analysis:
            body["analysis"] = analysis
        data = await self._post("/v1/env_params", body)
        return _extract_activity_id(data)

    async def fetch_api_key_usage(self) -> dict[str, Any]:
        if not self._live:
            return cached_usage()
        if self._upstream is not None:
            payload = await asyncio.to_thread(self._upstream.fetch_api_key_usage)
            return redact_value(payload)
        return redact_value(
            await self._post(
                "/v1/system/fetch-api-key-usage",
                {"api_key": self._settings.fortyguard_api_key},
            )
        )

    async def get_status(self, activity_id: str) -> dict[str, Any]:
        if not self._live:
            result = self._lookup_cache(activity_id)
            return {
                "error": False,
                "status_code": 200,
                "message": "Completed",
                "data": {"activity_id": activity_id, "status": "Completed", "result": result},
            }
        if self._upstream is not None:
            data = await asyncio.to_thread(self._upstream.get_status, activity_id)
            return {"data": data}
        client = await self._client()
        response = await client.get(f"/v1/status/{activity_id}")
        return _parse_json(response)

    async def wait_for_result(
        self,
        activity_id: str,
        *,
        timeout_seconds: float,
        initial_delay: float = 3.0,
        max_delay: float = 30.0,
        sleeper=asyncio.sleep,
    ) -> dict[str, Any]:
        delay = initial_delay
        elapsed = 0.0
        last: dict[str, Any] = {}
        while elapsed <= timeout_seconds:
            last = await self.get_status(activity_id)
            status = _status_of(last)
            if status in TERMINAL_SUCCESS:
                return last
            if status in TERMINAL_FAILURE:
                raise FortyGuardError(f"FortyGuard task {activity_id} failed with status={status}.")
            await sleeper(delay)
            elapsed += delay
            delay = min(delay * 2, max_delay)
        raise FortyGuardTimeout(
            f"FortyGuard task {activity_id} did not finish within {timeout_seconds:.0f}s "
            f"(last status={_status_of(last) or 'unknown'})."
        )

    def _lookup_cache(self, activity_id: str) -> dict[str, Any]:
        for bucket in self._cached_results.values():
            if activity_id in bucket:
                return bucket[activity_id]
        return cached_heatmap_result(analytic_type="tcm", threshold=None, label="unknown")

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._settings.fortyguard_base_url.rstrip("/"),
                headers={
                    "api-key": self._settings.fortyguard_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._http

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        response = await client.post(path, json=body)
        return _parse_json(response)


def _date_time_payload(spec: DateTimeSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {"start_date": spec.start_date, "filter_type": spec.filter_type}
    if spec.start_time:
        payload["start_time"] = spec.start_time
    if spec.end_time:
        payload["end_time"] = spec.end_time
    if spec.end_date:
        payload["end_date"] = spec.end_date
    return payload


def _parse_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise FortyGuardError(f"Non-JSON response ({response.status_code}): {response.text[:300]}") from exc
    if response.status_code >= 400:
        raise FortyGuardError(
            f"HTTP {response.status_code} from {response.request.url.path}: {payload}"
        )
    if isinstance(payload, dict) and payload.get("error") is True:
        raise FortyGuardError(str(payload))
    return payload if isinstance(payload, dict) else {"data": payload}


def _extract_activity_id(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        raise FortyGuardError(f"Unexpected submit payload: {payload!r}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    activity_id = data.get("activity_id") or payload.get("activity_id")
    if not activity_id:
        raise FortyGuardError("Submit response missing activity_id")
    return str(activity_id)


def _status_of(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return str(data.get("status") or payload.get("status") or "").lower()


def is_retryable_http(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE_STATUS:
        return True
    if isinstance(exc, FortyGuardError) and any(str(code) in str(exc) for code in RETRYABLE_STATUS):
        return True
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))
