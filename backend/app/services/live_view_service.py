"""
Live-view session setup: application lookup + Chrome session + connected
LiveViewProxy. Extracted from api/ws.py's live_view_ws handler — the actual
duplex message pump (reading frontend WS messages, forwarding frames) stays
in the route, since that's inherently coupled to the specific Starlette
WebSocket connection object, not a business-logic concern to relocate.
"""

from app.core.exceptions import NotFoundError
from app.repositories.application_repository import ApplicationRepository
from app.services.browser.chrome_launcher import ChromeSession, get_or_launch
from app.services.browser.live_view import LiveViewProxy


class LiveViewService:
    def __init__(self, application_repo: ApplicationRepository):
        self._applications = application_repo

    async def connect(self, application_id: str) -> LiveViewProxy:
        application = await self._applications.get(application_id)
        if application is None:
            raise NotFoundError("Application not found")

        session: ChromeSession = await get_or_launch(str(application.profile_id))
        proxy = LiveViewProxy(session)
        await proxy.connect()
        await proxy.start_screencast()
        return proxy
