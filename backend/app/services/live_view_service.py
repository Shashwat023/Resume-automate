"""
Live-view session setup: application lookup + Chrome session + connected
LiveViewProxy. Extracted from api/ws.py's live_view_ws handler — the actual
duplex message pump (reading frontend WS messages, forwarding frames) stays
in the route, since that's inherently coupled to the specific Starlette
WebSocket connection object, not a business-logic concern to relocate.
"""

from app.core.exceptions import ConflictError, NotFoundError
from app.domain import status as st
from app.repositories.application_repository import ApplicationRepository
from app.services.browser.chrome_launcher import ChromeSession, get_session
from app.services.browser.live_view import LiveViewProxy


class LiveViewService:
    def __init__(self, application_repo: ApplicationRepository):
        self._applications = application_repo

    async def connect(self, application_id: str) -> LiveViewProxy:
        application = await self._applications.get(application_id)
        if application is None:
            raise NotFoundError("Application not found")

        session: ChromeSession | None = get_session(str(application.profile_id))
        if (
            application.status not in (st.RUNNING, st.NEEDS_INPUT, st.PAUSED)
            or session is None
        ):
            raise ConflictError("No active browser session for this application")
        proxy = LiveViewProxy(session)
        await proxy.connect()
        await proxy.start_screencast()
        return proxy
