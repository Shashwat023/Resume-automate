"""
"Sync all tracked companies" — a background job separate from the manual
paste-a-URL flow (sync_service.sync_company, its own tests unchanged).
Exercises bulk_sync_service.py's pause/resume/completion logic directly
against an in-memory DB, faking sync_company() and the portals.yml seed
step so no real Chrome/LLM call is ever made.
"""

from datetime import datetime, timedelta, timezone

from app.models.db_models import TrackedCompany, TrackedCompanySyncState
from app.repositories.tracked_company_repository import TrackedCompanyRepository
from app.services.scraper import bulk_sync_service


class _CtxWrapper:
    """Same pattern test_engine_runner_2fa.py already uses: redirects a
    module's own `async_session_factory` reference to the test's
    in-memory `async_session`, since bulk_sync_service (like runner.py)
    opens its own sessions rather than receiving one via Depends(get_db)."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _patch_session(monkeypatch, async_session):
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", _CtxWrapper(async_session)
    )


def _patch_no_op_seed(monkeypatch):
    """Tests seed TrackedCompany rows directly — the real portals.yml
    seed step would try to read the actual file and hit the real
    (session-factory-bound) DB engine, neither of which these unit tests
    want."""

    async def _no_op():
        return {"total_in_file": 0, "inserted": 0, "updated": 0, "skipped": 0}

    monkeypatch.setattr(bulk_sync_service, "seed_tracked_companies", _no_op)


async def _add_company(async_session, name, url, *, enabled=True, last_synced_at=None):
    company = TrackedCompany(
        name=name, careers_url=url, enabled=enabled, last_synced_at=last_synced_at
    )
    async_session.add(company)
    await async_session.commit()
    return company


async def test_status_defaults_to_idle_before_anything_runs(async_session, monkeypatch):
    _patch_session(monkeypatch, async_session)

    status = await bulk_sync_service.get_status()

    assert status["status"] == "idle"
    assert status["total_eligible"] == 0
    assert status["processed"] == 0


async def test_run_loop_processes_every_eligible_company_and_stops_when_none_left(
    async_session, monkeypatch
):
    _patch_session(monkeypatch, async_session)
    await _add_company(async_session, "Acme", "https://acme.com/careers")
    await _add_company(async_session, "Globex", "https://globex.com/careers")

    calls = []

    async def fake_sync_company(url, db):
        calls.append(url)
        return {"success": True, "jobs_inserted": 3, "jobs_updated": 1, "failed": 0}

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company)

    # Prime state as an already-"running" fresh pass (what start_or_resume
    # would have set up) and run the loop directly — same "test the real
    # function, skip the fire-and-forget task wrapper" strategy
    # test_engine_runner_2fa.py already uses for run_application().
    repo = TrackedCompanyRepository(async_session)
    state = TrackedCompanySyncState(
        id=1,
        status="running",
        total_eligible=await repo.count_eligible(_far_future_cutoff()),
    )
    async_session.add(state)
    await async_session.commit()

    await bulk_sync_service._run_loop()

    assert sorted(calls) == ["https://acme.com/careers", "https://globex.com/careers"]

    final = await bulk_sync_service.get_status()
    assert final["status"] == "completed"
    assert final["processed"] == 2
    assert final["jobs_inserted"] == 6
    assert final["jobs_updated"] == 2
    assert final["companies_failed"] == 0
    assert final["current_company_name"] is None


async def test_run_loop_pauses_without_marking_when_credits_run_out(
    async_session, monkeypatch
):
    """Out of OpenRouter credits: the rest of the list must NOT be marked
    synced with 0 jobs — pause, and Resume retries the same company."""
    _patch_session(monkeypatch, async_session)
    await _add_company(async_session, "Acme", "https://acme.com/careers")
    await _add_company(async_session, "Globex", "https://globex.com/careers")
    calls = []

    async def fake_sync_company(url, db):
        calls.append(url)
        return {
            "success": False,
            "jobs_inserted": 0,
            "jobs_updated": 0,
            "failed": 1,
            "out_of_credits": True,
        }

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company)
    async_session.add(TrackedCompanySyncState(id=1, status="running", total_eligible=2))
    await async_session.commit()

    await bulk_sync_service._run_loop()

    assert len(calls) == 1  # stopped at the first company
    final = await bulk_sync_service.get_status()
    assert final["status"] == "paused"
    assert final["processed"] == 0 and final["companies_failed"] == 0
    repo = TrackedCompanyRepository(async_session)
    assert await repo.count_eligible(_far_future_cutoff()) == 2  # nothing marked synced


async def test_run_loop_stops_at_the_next_boundary_when_paused(
    async_session, monkeypatch
):
    _patch_session(monkeypatch, async_session)
    await _add_company(async_session, "Acme", "https://acme.com/careers")
    await _add_company(async_session, "Globex", "https://globex.com/careers")

    processed_order = []

    async def fake_sync_company(url, db):
        processed_order.append(url)
        # Request a pause partway through — simulates a Pause click
        # arriving while the loop is mid-company.
        if len(processed_order) == 1:
            bulk_sync_service._pause_requested.set()
        return {"success": True, "jobs_inserted": 1, "jobs_updated": 0, "failed": 0}

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company)

    state = TrackedCompanySyncState(id=1, status="running", total_eligible=2)
    async_session.add(state)
    await async_session.commit()

    try:
        await bulk_sync_service._run_loop()
    finally:
        bulk_sync_service._pause_requested.clear()

    assert len(processed_order) == 1  # stopped after finishing the current company
    status = await bulk_sync_service.get_status()
    assert status["status"] == "paused"
    assert status["processed"] == 1


async def test_a_failing_company_does_not_stop_the_pass_or_get_retried_immediately(
    async_session, monkeypatch
):
    """
    Live-relevant: a company that errors every time must still only cost
    one attempt per resync window, not one per loop iteration — otherwise
    a single broken site could consume an entire pass's budget retrying
    itself forever. mark_synced() runs regardless of success/failure,
    which is what prevents that.
    """
    _patch_session(monkeypatch, async_session)
    await _add_company(async_session, "Broken Co", "https://broken.example/careers")
    await _add_company(async_session, "Good Co", "https://good.example/careers")

    async def fake_sync_company(url, db):
        if "broken" in url:
            raise RuntimeError("Chrome failed to launch")
        return {"success": True, "jobs_inserted": 2, "jobs_updated": 0, "failed": 0}

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company)

    state = TrackedCompanySyncState(id=1, status="running", total_eligible=2)
    async_session.add(state)
    await async_session.commit()

    await bulk_sync_service._run_loop()

    status = await bulk_sync_service.get_status()
    assert status["status"] == "completed"
    assert status["processed"] == 2
    assert status["companies_failed"] == 1
    assert status["jobs_inserted"] == 2  # only Good Co's

    repo = TrackedCompanyRepository(async_session)
    broken = await repo.get_by_careers_url("https://broken.example/careers")
    assert broken.last_synced_at is not None  # won't be retried again this window


async def test_start_or_resume_skips_a_company_synced_within_the_resync_window(
    async_session, monkeypatch
):
    _patch_session(monkeypatch, async_session)
    _patch_no_op_seed(monkeypatch)
    recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    await _add_company(
        async_session,
        "Just Synced",
        "https://fresh.example/careers",
        last_synced_at=recent,
    )
    await _add_company(async_session, "Never Synced", "https://stale.example/careers")

    calls = []

    async def fake_sync_company(url, db):
        calls.append(url)
        return {"success": True, "jobs_inserted": 1, "jobs_updated": 0, "failed": 0}

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company)

    await bulk_sync_service.start_or_resume()
    await bulk_sync_service._active_task

    assert calls == ["https://stale.example/careers"]  # NOT the recently-synced one


async def test_start_or_resume_resets_counters_for_a_fresh_pass_but_not_a_resume(
    async_session, monkeypatch
):
    _patch_session(monkeypatch, async_session)
    _patch_no_op_seed(monkeypatch)

    async def fake_sync_company_noop(url, db):
        return {"success": True, "jobs_inserted": 0, "jobs_updated": 0, "failed": 0}

    monkeypatch.setattr(bulk_sync_service, "sync_company", fake_sync_company_noop)

    # A "paused" pass with existing progress must NOT have its counters
    # reset just by clicking Start again (that's a resume, not a restart).
    state = TrackedCompanySyncState(
        id=1, status="paused", total_eligible=10, processed=4, jobs_inserted=7
    )
    async_session.add(state)
    await async_session.commit()

    result = await bulk_sync_service.start_or_resume()
    await bulk_sync_service._active_task

    # Nothing eligible left to process (no companies seeded at all here),
    # so the loop immediately completes — the assertion of interest is
    # that resuming preserved the PRE-EXISTING counters up to that point.
    assert result["total_eligible"] == 10
    assert result["processed"] == 4
    assert result["jobs_inserted"] == 7


async def test_recover_stale_running_state_resets_to_paused(async_session, monkeypatch):
    _patch_session(monkeypatch, async_session)
    state = TrackedCompanySyncState(id=1, status="running")
    async_session.add(state)
    await async_session.commit()

    await bulk_sync_service.recover_stale_running_state_on_startup()

    status = await bulk_sync_service.get_status()
    assert status["status"] == "paused"


async def test_recover_leaves_a_genuinely_idle_state_alone(async_session, monkeypatch):
    _patch_session(monkeypatch, async_session)

    await bulk_sync_service.recover_stale_running_state_on_startup()

    status = await bulk_sync_service.get_status()
    assert status["status"] == "idle"


def _far_future_cutoff():
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1000)
