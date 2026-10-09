import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, apply, jobs, profile, resume, ws
from app.core.config import get_settings
from app.core.db import init_db
from app.core.exceptions import ConflictError, NotFoundError

settings = get_settings()

# Nothing else configures logging, so Python's default (WARNING) hid every
# INFO line the app writes — the scraper's "Extracted N jobs", iframe and
# explore steps never reached the terminal. Only the app's own loggers are
# raised; uvicorn, httpx and the rest keep their defaults.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )
    _app_logger.addHandler(_handler)
    _app_logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.resume_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.chrome_profiles_dir.mkdir(parents=True, exist_ok=True)
    await init_db()

    from app.services.engine.runner import run_application
    from app.worker.queue_runner import set_run_fn

    set_run_fn(run_application)

    # A "sync all tracked companies" pass found still marked "running" here
    # is necessarily a crash artifact — no background task survives a
    # server restart — so it's reset to "paused" rather than left claiming
    # a run is active that nothing is actually driving. See
    # bulk_sync_service.py's own docstring for why this state is persisted
    # (not an in-memory flag like the apply queue's pause/resume) in the
    # first place: a multi-hour, possibly multi-day operation has to
    # survive exactly this kind of restart.
    from app.services.scraper.bulk_sync_service import (
        recover_stale_running_state_on_startup,
    )

    await recover_stale_running_state_on_startup()

    yield


app = FastAPI(title="Career-Ops Automation Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Created here, not only in lifespan(): StaticFiles raises at construction
# if the directory is missing, and this mount runs at IMPORT time — before
# lifespan() ever gets a chance to create it. A fresh clone therefore died
# on startup with "RuntimeError: Directory '...' does not exist" (caught
# live, FLAGGED.md #34.2). lifespan() still creates it too, harmlessly.
settings.resume_storage_dir.mkdir(parents=True, exist_ok=True)

app.mount(
    "/storage/resumes",
    StaticFiles(directory=str(settings.resume_storage_dir)),
    name="resume-storage",
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(profile.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(apply.router)
app.include_router(admin.router)
app.include_router(ws.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
