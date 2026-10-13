import asyncio

from fastapi import WebSocketDisconnect

from app.api import ws


class _FakeSocket:
    def __init__(self, disconnect_after: float):
        self._disconnect_after = disconnect_after
        self.sent: list[dict] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        await asyncio.sleep(self._disconnect_after)
        raise WebSocketDisconnect()

    async def send_json(self, payload):
        self.sent.append(payload)


async def test_logs_socket_stops_polling_when_the_client_disconnects_quietly(
    async_session, monkeypatch
):
    class _Ctx:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(ws, "async_session_factory", lambda: _Ctx())
    socket = _FakeSocket(disconnect_after=0.05)

    # No events exist, so nothing is ever sent: the handler must still end.
    await asyncio.wait_for(ws.logs_ws(socket, "no-such-application"), timeout=3)

    assert socket.accepted is True
    assert socket.sent == []
