from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.jobs import create_job, get_job, run_job, to_report, to_status
from app.models.schemas import BriefRequest, JobAccepted, JobStatusResponse, ReportResponse

router = APIRouter()


import os

@router.post("/brief", response_model=JobAccepted)
async def submit_brief(payload: BriefRequest, background_tasks: BackgroundTasks) -> JobAccepted:
    record = create_job()
    if os.getenv("VERCEL"):
        await run_job(record.job_id, payload.brief, payload.as_of)
        return JobAccepted(job_id=record.job_id, status=record.status)
    else:
        background_tasks.add_task(run_job, record.job_id, payload.brief, payload.as_of)
        return JobAccepted(job_id=record.job_id, status="queued")


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str) -> JobStatusResponse:
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return to_status(record)


@router.get("/report/{job_id}", response_model=ReportResponse)
async def job_report(job_id: str) -> ReportResponse:
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    if record.status != "succeeded":
        if record.markdown:
            return to_report(record)
        raise HTTPException(
            status_code=409,
            detail=f"job is {record.status}: {record.error or 'no report available'}",
        )
    return to_report(record)
