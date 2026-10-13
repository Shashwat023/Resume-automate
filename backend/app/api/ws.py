import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.db import async_session_factory
from app.core.exceptions import ConflictError, NotFoundError
from app.repositories.application_repository import ApplicationRepository
from app.services.live_view_service import LiveViewService
from app.services.log_stream_service import LogStreamService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/apply/{application_id}/live-view")
async def live_view_ws(websocket: WebSocket, application_id: str) -> None:
    await websocket.accept()

    # Scoped narrowly to the lookup, same as before this restructure — the
    # session must not stay open for the whole (potentially long-lived)
    # live-view connection, only for the initial application lookup.
    try:
        async with async_session_factory() as db:
            live_view = LiveViewService(ApplicationRepository(db))
            proxy = await live_view.connect(application_id)
    except NotFoundError:
        await websocket.close(code=4404)
        return
    except ConflictError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=4409)
        return
    except Exception:  # noqa: BLE001 - websocket must fail closed, not launch Chrome
        logger.exception("Live view attach failed")
        await websocket.send_json(
            {"type": "error", "message": "Could not attach to the browser session"}
        )
        await websocket.close(code=4409)
        return

    async def pump_frames():
        async for frame_b64 in proxy.frames():
            metadata = proxy.last_metadata
            await websocket.send_json(
                {
                    "type": "frame",
                    "data": frame_b64,
                    "width": metadata.get("deviceWidth"),
                    "height": metadata.get("deviceHeight"),
                }
            )

    frame_task = asyncio.create_task(pump_frames())
    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "mouse":
                await proxy.dispatch_mouse(
                    msg["event"], msg["x"], msg["y"], msg.get("button", "left")
                )
            elif msg_type == "wheel":
                await proxy.dispatch_wheel(
                    msg["x"], msg["y"], msg.get("deltaX", 0), msg.get("deltaY", 0)
                )
            elif msg_type == "key":
                await proxy.dispatch_key(
                    msg["event"],
                    msg.get("text"),
                    msg.get("key"),
                    code=msg.get("code"),
                    key_code=msg.get("keyCode"),
                    modifiers=msg.get("modifiers"),
                )
    except WebSocketDisconnect:
        pass
    finally:
        frame_task.cancel()
        await proxy.close()


@router.websocket("/ws/apply/{application_id}/logs")
async def logs_ws(websocket: WebSocket, application_id: str) -> None:
    await websocket.accept()
    last_id = 0

    # Starlette only notices a client going away on receive()/send(). With no
    # new events nothing is ever sent, so without this reader a closed tab left
    # a 1 Hz DB poller running until the server restarted.
    async def _until_disconnect() -> None:
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    disconnect_task = asyncio.create_task(_until_disconnect())
    try:
        while not disconnect_task.done():
            # A fresh session per poll (not FastAPI Depends, which resolves once
            # per connection) is deliberate: it's what guarantees each iteration
            # sees data committed by other sessions since the last poll.
            async with async_session_factory() as db:
                service = LogStreamService(ApplicationRepository(db))
                events = await service.events_after(application_id, last_id)
            for event in events:
                await websocket.send_json(
                    {
                        "id": event.id,
                        "level": event.level,
                        "message": event.message,
                        "tier": event.tier,
                        "created_at": event.created_at.isoformat(),
                    }
                )
                last_id = event.id
            await asyncio.wait({disconnect_task}, timeout=1.0)
    except WebSocketDisconnect:
        pass
    finally:
        disconnect_task.cancel()
