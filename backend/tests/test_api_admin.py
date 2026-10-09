"""
Admin API surface: the pre-existing manual paste-a-URL sync route, and the
new "sync all tracked companies" endpoints (see bulk_sync_service.py).
"""

from app.services.scraper import bulk_sync_service


async def test_sync_tracked_status_defaults_to_idle(client, monkeypatch, async_session):
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", lambda: _Ctx(async_session)
    )

    resp = await client.get("/api/admin/sync-tracked/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["total_eligible"] == 0


async def test_manual_sync_is_blocked_while_a_bulk_sync_is_running(
    client, monkeypatch, async_session
):
    """
    Both this route and the bulk sync's own loop drive Stagehand through
    the SAME shared "scraper" Chrome profile — running both at once would
    race over that one browser session, exactly the class of bug
    FLAGGED.md #11/#26-29 already fought hard to eliminate elsewhere.
    """
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", lambda: _Ctx(async_session)
    )
    from app.models.db_models import TrackedCompanySyncState

    async_session.add(TrackedCompanySyncState(id=1, status="running"))
    await async_session.commit()

    resp = await client.post(
        "/api/admin/sync", json={"company_url": "https://example.com/careers"}
    )

    assert resp.status_code == 409


async def test_manual_sync_still_works_when_no_bulk_sync_is_running(
    client, monkeypatch, async_session
):
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", lambda: _Ctx(async_session)
    )

    async def fake_sync_company(url, db):
        return {"success": True, "jobs_inserted": 5, "jobs_updated": 0, "failed": 0}

    from app.api import admin

    monkeypatch.setattr(admin, "sync_company", fake_sync_company)

    resp = await client.post(
        "/api/admin/sync", json={"company_url": "https://example.com/careers"}
    )

    assert resp.status_code == 200
    assert resp.json()["jobs_inserted"] == 5


async def test_sync_tracked_start_and_status_round_trip(
    client, monkeypatch, async_session
):
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", lambda: _Ctx(async_session)
    )

    async def fake_seed():
        return {"total_in_file": 0, "inserted": 0, "updated": 0, "skipped": 0}

    monkeypatch.setattr(bulk_sync_service, "seed_tracked_companies", fake_seed)

    resp = await client.post("/api/admin/sync-tracked/start")

    assert resp.status_code == 200
    body = resp.json()
    # Nothing seeded -> nothing eligible -> the background loop completes
    # essentially immediately, but the call itself must not block on it.
    assert body["status"] in ("running", "completed")
    await bulk_sync_service._active_task


async def test_sync_tracked_pause_reports_paused_status(
    client, monkeypatch, async_session
):
    monkeypatch.setattr(
        bulk_sync_service, "async_session_factory", lambda: _Ctx(async_session)
    )
    from app.models.db_models import TrackedCompanySyncState

    async_session.add(TrackedCompanySyncState(id=1, status="running"))
    await async_session.commit()

    resp = await client.post("/api/admin/sync-tracked/pause")

    assert resp.status_code == 200
    # The endpoint only REQUESTS a pause (the in-memory flag) — the actual
    # status flip is the background loop's own job at its next boundary
    # check, which isn't running here at all, so the persisted status is
    # unchanged by this call alone. Covered in depth by
    # test_bulk_sync_service.py's test_run_loop_stops_at_the_next_boundary_when_paused.
    assert resp.json()["status"] == "running"
    assert bulk_sync_service._pause_requested.is_set()
    bulk_sync_service._pause_requested.clear()


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False
