from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.agent.graph import run_pipeline
from app.config import Settings, get_settings
from app.models.schemas import JobStatusResponse, ReportResponse, TaskPlan, utc_now


@dataclass
class JobRecord:
    job_id: str
    status: str = "queued"
    stage: str | None = "queued"
    error: str | None = None
    langsmith_url: str | None = None
    markdown: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    planner_model: str | None = None
    fortyguard_mode: str | None = None
    created_at: datetime = field(default_factory=utc_now)


JOBS: dict[str, JobRecord] = {}


def create_job() -> JobRecord:
    record = JobRecord(job_id=str(uuid4()))
    JOBS[record.job_id] = record
    return record


def get_job(job_id: str) -> JobRecord | None:
    return JOBS.get(job_id)


async def run_job(job_id: str, brief: str, as_of, settings: Settings | None = None) -> None:
    record = JOBS[job_id]
    record.status = "running"
    record.stage = "planner"
    try:
        result = await run_pipeline(brief, settings or get_settings(), as_of=as_of)
        record.stage = result.get("stage")
        record.langsmith_url = result.get("langsmith_url")
        record.markdown = result.get("markdown")
        record.citations = result.get("citations") or []
        record.plan = result.get("plan")
        record.planner_model = result.get("llm_model")
        record.fortyguard_mode = result.get("fortyguard_mode")
        exec_result = result.get("executor_result") or {}
        record.audit_trail = exec_result.get("calls") or []
        if result.get("error") and not record.markdown:
            record.status = "failed"
            record.error = result["error"]
        else:
            record.status = "succeeded"
            record.error = result.get("error")
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.stage = "failed"


def to_status(record: JobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,  # type: ignore[arg-type]
        stage=record.stage,
        error=record.error,
        langsmith_url=record.langsmith_url,
    )


def to_report(record: JobRecord) -> ReportResponse:
    plan = TaskPlan.model_validate(record.plan) if record.plan else None
    return ReportResponse(
        job_id=record.job_id,
        markdown=record.markdown or "",
        citations=record.citations,
        plan=plan,
        audit_trail=record.audit_trail,  # type: ignore[arg-type]
        langsmith_url=record.langsmith_url,
        planner_model=record.planner_model,
        fortyguard_mode=record.fortyguard_mode,
        created_at=record.created_at,
    )
