import asyncio
import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.db import async_session_factory
from app.models.db_models import Application, RunEvent
from app.services.browser.chrome_launcher import get_or_launch
from app.services.browser.live_view import LiveViewProxy

router = APIRouter()


@router.websocket("/ws/apply/{application_id}/live-view")
async def live_view_ws(websocket: WebSocket, application_id: str) -> None:
    await websocket.accept()

    async with async_session_factory() as db:
        application = await db.get(Application, application_id)
        if application is None:
            await websocket.close(code=4404)
            return
        profile_id = application.profile_id

    session = await get_or_launch(str(profile_id))
    proxy = LiveViewProxy(session)
    await proxy.connect()
    await proxy.start_screencast()

    async def pump_frames():
        async for frame_b64 in proxy.frames():
            await websocket.send_json({"type": "frame", "data": frame_b64})

    frame_task = asyncio.create_task(pump_frames())
    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "mouse":
                await proxy.dispatch_mouse(msg["event"], msg["x"], msg["y"], msg.get("button", "left"))
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
            async with async_session_factory() as db:
                stmt = (
                    select(RunEvent)
                    .where(RunEvent.application_id == application_id, RunEvent.id > last_id)
                    .order_by(RunEvent.id.asc())
                )
                events = (await db.execute(stmt)).scalars().all()
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
