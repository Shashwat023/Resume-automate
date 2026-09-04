from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---- Profile: matches frontend/src/api/profile.ts BackendProfile exactly ----


class ProfileBase(BaseModel):
    full_name: str
    email: str
    phone: str
    date_of_birth: str | None = None
    gender: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_of_experience: int | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    twitter_url: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    address: str | None = None
    postal_code: str | None = None
    citizenship: str | None = None
    visa_status: str | None = None
    sponsorship_required: bool | None = None
    highest_degree: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    preferred_job_title: str | None = None
    preferred_location: str | None = None
    expected_salary: str | None = None
    current_salary: str | None = None
    notice_period: str | None = None
    willing_to_relocate: bool | None = None
    skills: list[str] | None = None
    summary: str | None = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    """All fields optional for PUT (Partial<BackendProfile> on the frontend)."""

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_of_experience: int | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    twitter_url: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    address: str | None = None
    postal_code: str | None = None
    citizenship: str | None = None
    visa_status: str | None = None
    sponsorship_required: bool | None = None
    highest_degree: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    preferred_job_title: str | None = None
    preferred_location: str | None = None
    expected_salary: str | None = None
    current_salary: str | None = None
    notice_period: str | None = None
    willing_to_relocate: bool | None = None
    skills: list[str] | None = None
    summary: str | None = None


class ProfileOut(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---- Resume ----


class ResumeUploadOut(BaseModel):
    success: bool
    resume_url: str


class ResumeGetOut(BaseModel):
    profile_id: int
    resume_url: str
    uploaded_at: datetime


class DeleteOut(BaseModel):
    success: bool


# ---- Job: matches frontend/src/types/index.ts Job (id as string on the wire) ----


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    company_name: str
    location: str
    location_type: str | None = None
    industry: str | None = None
    posted_text: str | None = None
    posted_date: str | None = None
    job_type: str | None = None
    salary: str | None = None
    description: str | None = None
    requirements: list[str] | None = None
    status: str | None = None
    apply_url: str
    company_url: str | None = None
    ats: str | None = None


class JobSearchOut(BaseModel):
    jobs: list[JobOut]
    total: int
    page: int
    limit: int


# ---- Apply / Application ----


class ApplyStartIn(BaseModel):
    profile_id: int
    job_id: int


class ApplyStartOut(BaseModel):
    application_id: str
    status: str


class ApplyStatusOut(BaseModel):
    application_id: str
    status: str
    job_title: str | None = None
    company: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class ApplyHistoryItemOut(BaseModel):
    application_id: str
    job_id: int
    company_name: str | None = None
    job_title: str | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunEventOut(BaseModel):
    id: int
    level: str
    message: str
    tier: str | None = None
    created_at: datetime


class ApplyDetailsOut(BaseModel):
    application_id: str
    profile: dict
    job: dict
    status: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Day 5: full run_events timeline, so what happened on a job is visible
    # after the fact (completed/failed) — not just while it's live via the
    # logs WebSocket. Additive field; nothing in the frontend currently
    # depends on ApplyDetailsOut's exact shape (getDetails is unused there
    # today), so this doesn't touch the existing contract.
    events: list[RunEventOut] = []


# ---- Admin sync ----


class AdminSyncIn(BaseModel):
    company_url: str


class AdminSyncOut(BaseModel):
    success: bool
    jobs_inserted: int
    jobs_updated: int
    failed: int
