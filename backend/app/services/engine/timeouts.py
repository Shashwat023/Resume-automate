"""
One place for "no automation call may wait forever".

FLAGGED.md #15 was found as a Tier 2 problem — no bound on observe()/act()
— and fixed there. The same class of bug is present on every other await
that crosses the CDP/RPC boundary: `page.snapshot()`,
`page.wait_for_load_state()`, `page.goto()`. Those are not slow-by-design
LLM calls, but they DO talk to a browser over a socket that has been
observed wedging (`-32602 Invalid mouse button`, `RPC client is closed`),
and a wedged socket read has no timeout of its own. A single one of them
hanging strands the application, its Chrome session, and — because the run
holds the per-profile lock the whole time — every future application for
that profile too.

Two distinct budgets, because these are genuinely different kinds of wait:
  - PAGE_CALL: browser round-trips that should be near-instant. Generous
    relative to their real cost, still far below "looks like a hang".
  - LLM_CALL: reasoning calls, which legitimately take a long time (real
    observe() calls on qwen/qwen3.6-27b have been seen at ~78s live).
"""

import asyncio
from typing import Any, Coroutine

PAGE_CALL_TIMEOUT_SECONDS = 60
LLM_CALL_TIMEOUT_SECONDS = 120


def describe(exc: BaseException) -> str:
    """`TimeoutError`'s `str()` is empty — the exact "silent failure" shape
    already fixed once in runner.py. Without the type name a timeout logs
    as "... failed: " with nothing after it, which is precisely the log
    line that made a real timeout look like a mystery."""
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


async def with_timeout(
    coro: Coroutine[Any, Any, Any],
    seconds: float = PAGE_CALL_TIMEOUT_SECONDS,
    what: str = "browser call",
) -> Any:
    """Raises TimeoutError with a message naming WHICH call timed out — a
    bare `TimeoutError()` from deep in the cascade is nearly unactionable
    when there are a dozen candidate await points."""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except TimeoutError as exc:
        raise TimeoutError(f"{what} exceeded {seconds}s") from exc
