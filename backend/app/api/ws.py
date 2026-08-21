import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.db import async_session_factory
from app.core.exceptions import NotFoundError
from app.repositories.application_repository import ApplicationRepository
from app.services.live_view_service import LiveViewService
from app.services.log_stream_service import LogStreamService

router = APIRouter()


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

    async def pump_frames():
        async for frame_b64 in proxy.frames():
            await websocket.send_json({"type": "frame", "data": frame_b64})

    frame_task = asyncio.create_task(pump_frames())
    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "mouse":
                await proxy.dispatch_mouse(
                    msg["event"], msg["x"], msg["y"], msg.get("button", "left")
                )
            elif msg_type == "key":
                await proxy.dispatch_key(msg["event"], msg.get("text"), msg.get("key"))
    except WebSocketDisconnect:
        pass
    finally:
        frame_task.cancel()
        await proxy.close()


@router.websocket("/ws/apply/{application_id}/logs")
async def logs_ws(websocket: WebSocket, application_id: str) -> None:
    await websocket.accept()
    last_id = 0
    try:
        while True:
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
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
