"""
Live-view proxy: a SECOND, independent CDP client on the same Chrome that
Stagehand is driving (session #1). Streams JPEG screencast frames out,
forwards mouse/keyboard input back in. This is the human-takeover surface
for the needs_input state (login/2FA/CAPTCHA) — see PLAN.md "The key trick".

Page domain methods (startScreencast, etc) must run in a session scoped to
a specific page target, not the top-level browser connection — so this
attaches to a page target with Target.attachToTarget(flatten=True) and
tags every subsequent command with that sessionId (CDP "flat session" mode).

A single background reader task owns the socket's recv() loop and fans
messages out to command-reply futures / a frame queue — `websockets`
raises ConcurrencyError if two coroutines call recv() on the same
connection at once (send() waiting for a reply, and a frames() generator
consuming the stream, would otherwise race for every incoming message).
"""

import asyncio
import itertools
import json
from collections.abc import AsyncIterator
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from app.services.browser.chrome_launcher import ChromeSession


class LiveViewProxy:
    def __init__(self, session: ChromeSession):
        self._session = session
        self._ws: ClientConnection | None = None
        self._id_counter = itertools.count(1)
        self._page_session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._frame_queue: asyncio.Queue[str] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def connect(self) -> None:
        import urllib.request

        with urllib.request.urlopen(
            f"{self._session.cdp_url}/json/version", timeout=2
        ) as resp:
            info = json.loads(resp.read())
        self._ws = await websockets.connect(info["webSocketDebuggerUrl"], max_size=None)
        self._reader_task = asyncio.create_task(self._read_loop())

        targets = (await self._call("Target.getTargets")).get("targetInfos", [])
        page_target = next((t for t in targets if t.get("type") == "page"), None)
        if page_target is None:
            created = await self._call("Target.createTarget", {"url": "about:blank"})
            target_id = created["targetId"]
        else:
            target_id = page_target["targetId"]

        attached = await self._call(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        self._page_session_id = attached["sessionId"]

    async def _read_loop(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            data = json.loads(raw)
            msg_id = data.get("id")
            if msg_id is not None and msg_id in self._pending:
                future = self._pending.pop(msg_id)
                if not future.done():
                    if "error" in data:
                        future.set_exception(RuntimeError(str(data["error"])))
                    else:
                        future.set_result(data.get("result", {}))
                continue
            if (
                data.get("method") == "Page.screencastFrame"
                and data.get("sessionId") == self._page_session_id
            ):
                params = data["params"]
                await self._frame_queue.put(params["data"])
                await self._send_no_wait(
                    "Page.screencastFrameAck",
                    {"sessionId": params["sessionId"]},
                    session_scoped=True,
                )

    async def _send_no_wait(
        self, method: str, params: dict, *, session_scoped: bool
    ) -> None:
        assert self._ws is not None
        envelope: dict[str, Any] = {
            "id": next(self._id_counter),
            "method": method,
            "params": params,
        }
        if session_scoped:
            envelope["sessionId"] = self._page_session_id
        await self._ws.send(json.dumps(envelope))

    async def _call(
        self, method: str, params: dict | None = None, *, session_scoped: bool = False
    ) -> dict:
        assert self._ws is not None
        msg_id = next(self._id_counter)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        envelope: dict[str, Any] = {
            "id": msg_id,
            "method": method,
            "params": params or {},
        }
        if session_scoped:
            envelope["sessionId"] = self._page_session_id
        await self._ws.send(json.dumps(envelope))
        return await future

    async def send(self, method: str, params: dict | None = None) -> dict:
        """Command scoped to the attached page session (flat session mode)."""
        return await self._call(method, params, session_scoped=True)

    async def start_screencast(self) -> None:
        await self.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 60,
                "maxWidth": 1280,
                "maxHeight": 800,
                "everyNthFrame": 1,
            },
        )

    async def frames(self) -> AsyncIterator[str]:
        """Yields base64 JPEG frames, fed by the single background reader loop."""
        while True:
            yield await self._frame_queue.get()

    async def dispatch_mouse(
        self, event_type: str, x: float, y: float, button: str = "left"
    ) -> None:
        await self.send(
            "Input.dispatchMouseEvent",
            {"type": event_type, "x": x, "y": y, "button": button, "clickCount": 1},
        )

    async def dispatch_key(
        self, event_type: str, text: str | None, key: str | None
    ) -> None:
        params: dict[str, Any] = {"type": event_type}
        if text is not None:
            params["text"] = text
        if key is not None:
            params["key"] = key
        await self.send("Input.dispatchKeyEvent", params)

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._ws is not None:
            await self._ws.close()
