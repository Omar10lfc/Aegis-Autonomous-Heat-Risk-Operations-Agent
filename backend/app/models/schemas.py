from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisLayer(str, Enum):
    SNAPSHOT = "snapshot"
    EXCEEDANCE = "exceedance"
    PERSISTENCE = "persistence"


class FortyGuardEndpoint(str, Enum):
    HEATMAP = "/v1/heatmap"
    ENV_PARAMS = "/v1/env_params"
    USAGE = "/v1/system/fetch-api-key-usage"
    STATUS = "/v1/status/{activity_id}"


class DateTimeSpec(BaseModel):
    """Matches FortyGuard date_time objects on heatmap and env_params."""

    start_date: str
    filter_type: int
    start_time: str | None = None
    end_time: str | None = None
    end_date: str | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def yyyy_mm_dd(cls, value: str | None) -> str | None:
        if value is None:
            return value
        datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def hh_mm(cls, value: str | None) -> str | None:
        if value is None:
            return value
        datetime.strptime(value, "%H:%M")
        return value


class HeatmapJobSpec(BaseModel):
    endpoint: Literal["/v1/heatmap"] = "/v1/heatmap"
    polygon_aoi: dict[str, Any]
    date_time: DateTimeSpec
    granularity: int = 100
    analytic_type: Literal["tcm", "time_of_measure", "exceedance", "persistence"] = "tcm"
    threshold: float | None = None
    direction: Literal["above", "below"] | None = None
    label: str = "heatmap"


class EnvParamsJobSpec(BaseModel):
    endpoint: Literal["/v1/env_params"] = "/v1/env_params"
    latitude: float
    longitude: float
    temperature: float
    date_time: DateTimeSpec
    analysis: list[str] | None = Field(
        default=None,
        description="Basic/Startup plans allow at most 3 names. Omit to request the plan default.",
    )
    label: str = "env_params"


class TaskPlan(BaseModel):
    brief: str
    analysis_layer: AnalysisLayer
    rationale: str
    heatmap_jobs: list[HeatmapJobSpec] = Field(default_factory=list)
    env_params_jobs: list[EnvParamsJobSpec] = Field(default_factory=list)
    heat_threshold_celsius: float | None = 35.0
    client_framing: Literal["logistics", "insurance", "real_estate", "other"] = "logistics"


class ExecutorCallRecord(BaseModel):
    label: str
    endpoint: str
    activity_id: str | None = None
    status: str
    attempts: int = 1
    error: str | None = None
    result: dict[str, Any] | None = None


class ExecutorResult(BaseModel):
    calls: list[ExecutorCallRecord]
    usage: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)


class BriefRequest(BaseModel):
    brief: str = Field(min_length=8, max_length=8000)
    as_of: date | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded"] = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: str | None = None
    error: str | None = None
    langsmith_url: str | None = None


class ReportResponse(BaseModel):
    job_id: str
    markdown: str
    citations: list[dict[str, Any]]
    plan: TaskPlan | None = None
    audit_trail: list[ExecutorCallRecord] = Field(default_factory=list)
    langsmith_url: str | None = None
    planner_model: str | None = None
    fortyguard_mode: str | None = None
    created_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def forecast_horizon() -> datetime:
    return utc_now() + timedelta(hours=12)


HANDBOOK_MIN_DATE = date(2021, 1, 1)
DOCS_MIN_DATE = date(2019, 1, 1)
# Use the stricter handbook floor unless the live key proves 2019-era history is billed.
MIN_ALLOWED_DATE = HANDBOOK_MIN_DATE
MAX_AOI_KM2_HANDBOOK = 130.0
MI2_PER_KM2 = 0.386102
ALLOWED_GRANULARITIES = {60, 80, 100}
TERMINAL_SUCCESS = {"succeeded", "completed"}
TERMINAL_FAILURE = {"failed", "error"}
