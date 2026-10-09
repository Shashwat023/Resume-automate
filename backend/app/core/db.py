from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    from app.models import db_models  # noqa: F401  ensure models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn) -> None:
    """
    create_all() creates missing TABLES but never alters existing ones, so a
    column added to a model later made every query on an older app.db fail
    with "no such column" (live: tracked_companies.last_error). Add any
    missing nullable column in place — data is kept, and it's a no-op once
    the schema matches. Only additive; never drops or changes columns.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or not column.nullable:
                continue
            col_type = column.type.compile(dialect=sync_conn.dialect)
            sync_conn.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}')
            )


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
