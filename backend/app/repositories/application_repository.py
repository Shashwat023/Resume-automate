"""
All SQLAlchemy query construction for Application and RunEvent lives here.
Extracted verbatim from what was inline across api/apply.py and the
log-tailing loop in api/ws.py.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Application, Job, RunEvent


class ApplicationRepository:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, application_id: str) -> Application | None:
        return await self._db.get(Application, application_id)

    async def create(self, profile_id: int, job_id: int, status: str) -> Application:
        application = Application(profile_id=profile_id, job_id=job_id, status=status)
        self._db.add(application)
        await self._db.flush()
        return application

    async def add_event(
        self,
        application_id: str,
        message: str,
        *,
        level: str = "info",
        tier: str | None = None,
    ) -> None:
        self._db.add(
            RunEvent(
                application_id=application_id, message=message, level=level, tier=tier
            )
        )

    async def commit(self) -> None:
        await self._db.commit()

    async def refresh(self, application: Application) -> None:
        await self._db.refresh(application)

    async def history_with_job(self, profile_id: int) -> list[tuple[Application, Job]]:
        stmt = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(Application.profile_id == profile_id)
            .order_by(Application.created_at.desc())
        )
        return list((await self._db.execute(stmt)).all())

    async def events_after(self, application_id: str, last_id: int) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.application_id == application_id, RunEvent.id > last_id)
            .order_by(RunEvent.id.asc())
        )
        return list((await self._db.execute(stmt)).scalars().all())
