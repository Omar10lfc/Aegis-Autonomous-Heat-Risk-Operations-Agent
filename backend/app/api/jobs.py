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


import json
import os
import tempfile
from pathlib import Path

JOBS: dict[str, JobRecord] = {}
CACHE_FILE = Path(tempfile.gettempdir()) / "aegis_jobs_cache.json"


def _save_cache():
    try:
        data = {}
        for k, v in JOBS.items():
            data[k] = {
                "job_id": v.job_id,
                "status": v.status,
                "stage": v.stage,
                "error": v.error,
                "langsmith_url": v.langsmith_url,
                "markdown": v.markdown,
                "citations": v.citations,
                "plan": v.plan,
                "audit_trail": v.audit_trail,
                "planner_model": v.planner_model,
                "fortyguard_mode": v.fortyguard_mode,
                "created_at": v.created_at.isoformat(),
            }
        CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _load_cache():
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            for k, v in data.items():
                if k not in JOBS:
                    JOBS[k] = JobRecord(
                        job_id=v["job_id"],
                        status=v.get("status", "queued"),
                        stage=v.get("stage"),
                        error=v.get("error"),
                        langsmith_url=v.get("langsmith_url"),
                        markdown=v.get("markdown"),
                        citations=v.get("citations") or [],
                        plan=v.get("plan"),
                        audit_trail=v.get("audit_trail") or [],
                        planner_model=v.get("planner_model"),
                        fortyguard_mode=v.get("fortyguard_mode"),
                        created_at=datetime.fromisoformat(v["created_at"]) if v.get("created_at") else utc_now(),
                    )
    except Exception:
        pass


def create_job() -> JobRecord:
    _load_cache()
    record = JobRecord(job_id=str(uuid4()))
    JOBS[record.job_id] = record
    _save_cache()
    return record


def get_job(job_id: str) -> JobRecord | None:
    _load_cache()
    return JOBS.get(job_id)


async def run_job(job_id: str, brief: str, as_of, settings: Settings | None = None) -> None:
    _load_cache()
    record = JOBS.get(job_id)
    if not record:
        record = JobRecord(job_id=job_id)
        JOBS[job_id] = record
    record.status = "running"
    record.stage = "planner"
    _save_cache()
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
    finally:
        _save_cache()


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
