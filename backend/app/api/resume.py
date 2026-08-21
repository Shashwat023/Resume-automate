from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.models.db_models import Profile, Resume
from app.models.schemas import DeleteOut, ResumeGetOut, ResumeUploadOut

router = APIRouter(prefix="/api/resume", tags=["resume"])
settings = get_settings()


@router.post("/upload", response_model=ResumeUploadOut)
async def upload_resume(
    profile_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ResumeUploadOut:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile_dir = settings.resume_storage_dir / str(profile_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "resume"
    dest_path = profile_dir / filename
    contents = await file.read()
    dest_path.write_bytes(contents)

    resume_url = f"/storage/resumes/{profile_id}/{filename}"

    resume = await db.get(Resume, profile_id)
    if resume is None:
        resume = Resume(profile_id=profile_id, file_path=str(dest_path), resume_url=resume_url)
        db.add(resume)
    else:
        resume.file_path = str(dest_path)
        resume.resume_url = resume_url

    await db.commit()
    return ResumeUploadOut(success=True, resume_url=resume_url)


@router.get("/{profile_id}", response_model=ResumeGetOut)
async def get_resume(profile_id: int, db: AsyncSession = Depends(get_db)) -> Resume:
    resume = await db.get(Resume, profile_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.delete("/{profile_id}", response_model=DeleteOut)
async def delete_resume(profile_id: int, db: AsyncSession = Depends(get_db)) -> DeleteOut:
    resume = await db.get(Resume, profile_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    file_path = Path(resume.file_path)
    if file_path.exists():
        file_path.unlink()
    await db.delete(resume)
    await db.commit()
    return DeleteOut(success=True)
