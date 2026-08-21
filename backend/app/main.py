from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import admin, apply, jobs, profile, resume, ws
from app.core.config import get_settings
from app.core.db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.resume_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.chrome_profiles_dir.mkdir(parents=True, exist_ok=True)
    await init_db()

    from app.services.engine.runner import run_application
    from app.worker.queue_runner import set_run_fn

    set_run_fn(run_application)

    yield


app = FastAPI(title="Career-Ops Automation Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/storage/resumes",
    StaticFiles(directory=str(settings.resume_storage_dir)),
    name="resume-storage",
)

app.include_router(profile.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(apply.router)
app.include_router(admin.router)
app.include_router(ws.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
