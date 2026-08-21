import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Profile(Base):
    """Matches frontend/src/api/profile.ts BackendProfile exactly."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)

    date_of_birth: Mapped[str | None] = mapped_column(Text, default=None)
    gender: Mapped[str | None] = mapped_column(Text, default=None)
    current_title: Mapped[str | None] = mapped_column(Text, default=None)
    current_company: Mapped[str | None] = mapped_column(Text, default=None)
    years_of_experience: Mapped[int | None] = mapped_column(default=None)
    linkedin_url: Mapped[str | None] = mapped_column(Text, default=None)
    github_url: Mapped[str | None] = mapped_column(Text, default=None)
    portfolio_url: Mapped[str | None] = mapped_column(Text, default=None)
    twitter_url: Mapped[str | None] = mapped_column(Text, default=None)
    country: Mapped[str | None] = mapped_column(Text, default=None)
    state: Mapped[str | None] = mapped_column(Text, default=None)
    city: Mapped[str | None] = mapped_column(Text, default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    postal_code: Mapped[str | None] = mapped_column(Text, default=None)
    citizenship: Mapped[str | None] = mapped_column(Text, default=None)
    visa_status: Mapped[str | None] = mapped_column(Text, default=None)
    sponsorship_required: Mapped[bool | None] = mapped_column(default=None)
    highest_degree: Mapped[str | None] = mapped_column(Text, default=None)
    university: Mapped[str | None] = mapped_column(Text, default=None)
    graduation_year: Mapped[int | None] = mapped_column(default=None)
    preferred_job_title: Mapped[str | None] = mapped_column(Text, default=None)
    preferred_location: Mapped[str | None] = mapped_column(Text, default=None)
    expected_salary: Mapped[str | None] = mapped_column(Text, default=None)
    current_salary: Mapped[str | None] = mapped_column(Text, default=None)
    notice_period: Mapped[str | None] = mapped_column(Text, default=None)
    willing_to_relocate: Mapped[bool | None] = mapped_column(default=None)
    skills: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    resume: Mapped["Resume | None"] = relationship(back_populates="profile", uselist=False)
    applications: Mapped[list["Application"]] = relationship(back_populates="profile")


class Resume(Base):
    __tablename__ = "resumes"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    file_path: Mapped[str] = mapped_column(Text)
    resume_url: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    profile: Mapped["Profile"] = relationship(back_populates="resume")


class Job(Base):
    """Matches frontend/src/types/index.ts Job (id serialized as string on the wire)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    company_name: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text, default="")
    location_type: Mapped[str | None] = mapped_column(Text, default=None)  # Remote/Hybrid/Onsite
    industry: Mapped[str | None] = mapped_column(Text, default=None)
    posted_text: Mapped[str | None] = mapped_column(Text, default=None)
    posted_date: Mapped[str | None] = mapped_column(Text, default=None)
    job_type: Mapped[str | None] = mapped_column(Text, default=None)
    salary: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    requirements: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(Text, default="active")
    apply_url: Mapped[str] = mapped_column(Text)
    company_url: Mapped[str | None] = mapped_column(Text, default=None)
    ats: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("apply_url", name="uq_jobs_apply_url"),)


class Application(Base):
    """
    status vocabulary: queued, pending, checking_url, rescraped_retry_queued,
    link_expired_rescraping, running, needs_input, completed, success, failed,
    error, link_expired_rescraped_still_unavailable, cancelled
    (see frontend/src/api/queue.ts mapBackendStatusToJobStatus)
    """

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)  # application_id, external
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(Text, default="queued")
    pause_reason: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    profile: Mapped["Profile"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship()
    events: Mapped[list["RunEvent"]] = relationship(
        back_populates="application", order_by="RunEvent.created_at"
    )


class RunEvent(Base):
    """Append-only audit log per application; also the source for the log-stream WS."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(Text, default="info")  # info | warn | error
    message: Mapped[str] = mapped_column(Text)
    tier: Mapped[str | None] = mapped_column(Text, default=None)  # tier0|tier1|tier2|tier3
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped["Application"] = relationship(back_populates="events")


class FieldCache(Base):
    """(provider, form_signature) -> resolved field->selector map."""

    __tablename__ = "field_cache"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    form_signature: Mapped[str] = mapped_column(Text, primary_key=True)
    selector_map: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    hits: Mapped[int] = mapped_column(default=0)


class AnswerLibrary(Base):
    """question_hash -> user-approved answer, scoped per profile."""

    __tablename__ = "answers_library"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    question_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    question_text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TrackedCompany(Base):
    """Seeded from config/portals.yml."""

    __tablename__ = "tracked_companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    careers_url: Mapped[str] = mapped_column(Text, unique=True)
    ats: Mapped[str | None] = mapped_column(Text, default=None)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
