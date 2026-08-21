from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_resume_service
from app.models.schemas import DeleteOut, ResumeGetOut, ResumeUploadOut
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/api/resume", tags=["resume"])


@router.post("/upload", response_model=ResumeUploadOut)
async def upload_resume(
    profile_id: int = Form(...),
    file: UploadFile = File(...),
    service: ResumeService = Depends(get_resume_service),
) -> ResumeUploadOut:
    contents = await file.read()
    resume_url = await service.upload(profile_id, file.filename or "resume", contents)
    return ResumeUploadOut(success=True, resume_url=resume_url)


@router.get("/{profile_id}", response_model=ResumeGetOut)
async def get_resume(
    profile_id: int, service: ResumeService = Depends(get_resume_service)
) -> ResumeGetOut:
    return await service.get(profile_id)


@router.delete("/{profile_id}", response_model=DeleteOut)
async def delete_resume(
    profile_id: int, service: ResumeService = Depends(get_resume_service)
) -> DeleteOut:
    await service.delete(profile_id)
    return DeleteOut(success=True)
