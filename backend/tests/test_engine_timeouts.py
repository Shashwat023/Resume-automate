import asyncio

import pytest

from app.services.engine import timeouts


async def test_with_timeout_uses_the_current_default_when_not_explicit(monkeypatch):
    monkeypatch.setattr(timeouts, "PAGE_CALL_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(TimeoutError, match="timed call exceeded 0.01s"):
        await timeouts.with_timeout(asyncio.sleep(1), what="timed call")
