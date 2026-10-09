import httpx
import pytest

from app.services.engine import llm_client


def _respond_with(monkeypatch, status, text):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=text))
    real_client = httpx.AsyncClient

    monkeypatch.setattr(
        llm_client.httpx, "AsyncClient",
        lambda *a, **kw: real_client(transport=transport, **kw),
    )
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "test-key")
    llm_client.clear_credits_exhausted()


@pytest.mark.parametrize(
    "status,text,exhausted",
    [
        (402, '{"error":{"message":"Insufficient credits","code":402}}', True),
        (403, '{"error":{"message":"Key limit exceeded (total limit).","code":403}}', True),
        (403, '{"error":{"message":"Forbidden","code":403}}', False),
        (502, '{"error":{"message":"Provider returned error","code":502}}', False),
    ],
)
async def test_out_of_credits_is_flagged_for_402_and_a_403_key_limit(
    monkeypatch, status, text, exhausted
):
    _respond_with(monkeypatch, status, text)

    with pytest.raises(RuntimeError):
        await llm_client._call_openrouter({"model": "m", "messages": []})

    assert bool(llm_client.credits_exhausted()) is exhausted
    llm_client.clear_credits_exhausted()
