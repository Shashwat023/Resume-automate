"""
All SQLAlchemy query construction for Application and RunEvent lives here.
Extracted verbatim from what was inline across api/apply.py and the
log-tailing loop in api/ws.py.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import status as st
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

    async def find_blocking_for_job(
        self, profile_id: int, job_id: int
    ) -> Application | None:
        stmt = (
            select(Application)
            .where(
                Application.profile_id == profile_id,
                Application.job_id == job_id,
                Application.status.not_in((st.FAILED, st.CANCELLED)),
            )
            .order_by(Application.created_at.desc())
        )
        return (await self._db.execute(stmt)).scalars().first()

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

    async def delete_terminal_for_profile(
        self, profile_id: int, terminal_statuses: set[str]
    ) -> int:
        """Delete completed history while preserving queued or active runs."""
        application_ids = list(
            (
                await self._db.execute(
                    select(Application.id).where(
                        Application.profile_id == profile_id,
                        Application.status.in_(terminal_statuses),
                    )
                )
            ).scalars()
        )
        if not application_ids:
            return 0

        # Delete explicitly rather than relying on SQLite foreign-key pragma
        # configuration for RunEvent's ON DELETE CASCADE behavior.
        await self._db.execute(
            delete(RunEvent).where(RunEvent.application_id.in_(application_ids))
        )
        result = await self._db.execute(
            delete(Application).where(Application.id.in_(application_ids))
        )
        return result.rowcount or 0

    async def events_after(self, application_id: str, last_id: int) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.application_id == application_id, RunEvent.id > last_id)
            .order_by(RunEvent.id.asc())
        )
        return list((await self._db.execute(stmt)).scalars().all())
