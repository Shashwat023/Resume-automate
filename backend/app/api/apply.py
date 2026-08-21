from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import status as st
from app.core.db import get_db
from app.models.db_models import Application, Job, Profile, RunEvent
from app.models.schemas import (
    ApplyDetailsOut,
    ApplyHistoryItemOut,
    ApplyStartIn,
    ApplyStartOut,
    ApplyStatusOut,
)
from app.worker.queue_runner import enqueue_application

router = APIRouter(prefix="/api/apply", tags=["apply"])


@router.post("/start", response_model=ApplyStartOut)
async def start_apply(payload: ApplyStartIn, db: AsyncSession = Depends(get_db)) -> ApplyStartOut:
    profile = await db.get(Profile, payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    job = await db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    application = Application(
        profile_id=payload.profile_id,
        job_id=payload.job_id,
        status=st.QUEUED,
    )
    db.add(application)
    await db.flush()
    db.add(RunEvent(application_id=application.id, message="Application queued", tier=None))
    await db.commit()
    await db.refresh(application)

    await enqueue_application(application.id)

    return ApplyStartOut(application_id=application.id, status=application.status)


@router.get("/status/{application_id}", response_model=ApplyStatusOut)
async def get_apply_status(
    application_id: str, db: AsyncSession = Depends(get_db)
) -> ApplyStatusOut:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    job = await db.get(Job, application.job_id)
    return ApplyStatusOut(
        application_id=application.id,
        status=application.status,
        job_title=job.title if job else None,
        company=job.company_name if job else None,
        started_at=application.started_at,
        finished_at=application.finished_at,
        error=application.error,
    )


@router.get("/history/{profile_id}", response_model=list[ApplyHistoryItemOut])
async def get_apply_history(
    profile_id: int, db: AsyncSession = Depends(get_db)
) -> list[ApplyHistoryItemOut]:
    stmt = (
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.profile_id == profile_id)
        .order_by(Application.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ApplyHistoryItemOut(
            application_id=app.id,
            company_name=job.company_name,
            job_title=job.title,
            status=app.status,
            started_at=app.started_at,
            finished_at=app.finished_at,
        )
        for app, job in rows
    ]


@router.get("/details/{application_id}", response_model=ApplyDetailsOut)
async def get_apply_details(
    application_id: str, db: AsyncSession = Depends(get_db)
) -> ApplyDetailsOut:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    profile = await db.get(Profile, application.profile_id)
    job = await db.get(Job, application.job_id)
    return ApplyDetailsOut(
        application_id=application.id,
        profile={"id": profile.id, "full_name": profile.full_name} if profile else {},
        job={"id": job.id, "title": job.title, "company_name": job.company_name} if job else {},
        status=application.status,
        error=application.error,
        started_at=application.started_at,
        finished_at=application.finished_at,
    )


# ---- New: real pause/resume/cancel (frontend/src/features/queue/components/QueueControls.tsx) ----


@router.post("/{application_id}/pause", response_model=ApplyStatusOut)
async def pause_apply(application_id: str, db: AsyncSession = Depends(get_db)) -> ApplyStatusOut:
    application = await _require_active(application_id, db)
    application.status = st.NEEDS_INPUT
    application.pause_reason = "manual_pause"
    db.add(RunEvent(application_id=application.id, message="Paused by user"))
    await db.commit()
    return await get_apply_status(application_id, db)


@router.post("/{application_id}/resume", response_model=ApplyStatusOut)
async def resume_apply(application_id: str, db: AsyncSession = Depends(get_db)) -> ApplyStatusOut:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status not in (st.NEEDS_INPUT,):
        raise HTTPException(status_code=409, detail="Application is not paused")
    application.status = st.RUNNING
    application.pause_reason = None
    db.add(RunEvent(application_id=application.id, message="Resumed by user"))
    await db.commit()
    from app.worker.queue_runner import signal_resume

    await signal_resume(application_id)
    return await get_apply_status(application_id, db)


@router.post("/{application_id}/cancel", response_model=ApplyStatusOut)
async def cancel_apply(application_id: str, db: AsyncSession = Depends(get_db)) -> ApplyStatusOut:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status in st.TERMINAL:
        raise HTTPException(status_code=409, detail="Application already finished")
    application.status = st.CANCELLED
    application.finished_at = datetime.now(timezone.utc)
    db.add(RunEvent(application_id=application.id, message="Cancelled by user"))
    await db.commit()
    from app.worker.queue_runner import signal_cancel

    await signal_cancel(application_id)
    return await get_apply_status(application_id, db)


async def _require_active(application_id: str, db: AsyncSession) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status in st.TERMINAL:
        raise HTTPException(status_code=409, detail="Application already finished")
    return application
