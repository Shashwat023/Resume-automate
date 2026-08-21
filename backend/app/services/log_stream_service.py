"""
Log-tailing use case for the /ws/apply/{id}/logs WebSocket. Extracted from
api/ws.py's logs_ws handler — the polling loop (sleep + repeat) stays in
the route since it's driven by the WebSocket connection's lifetime; this
just answers "what's new since last_id".
"""

from app.models.db_models import RunEvent
from app.repositories.application_repository import ApplicationRepository


class LogStreamService:
    def __init__(self, application_repo: ApplicationRepository):
        self._applications = application_repo

    async def events_after(self, application_id: str, last_id: int) -> list[RunEvent]:
        return await self._applications.events_after(application_id, last_id)
