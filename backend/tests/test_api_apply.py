"""
Full apply lifecycle through real HTTP. The test client doesn't run the
app's lifespan (see conftest.py), so queue_runner's _run_fn stays unset and
enqueue_application() is a safe no-op — no real Chrome session is launched,
but the actual state-machine, status codes, and error messages are all
exercised for real.
"""


async def _create_profile_and_job(client):
    profile = (
        await client.post(
            "/api/profile",
            json={
                "full_name": "Jordan Smith",
                "email": "j@example.com",
                "phone": "123",
            },
        )
    ).json()

    # No job-creation endpoint exists (jobs only arrive via the scraper), so
    # seed one directly the same way admin/sync would.
    from app.core.db import get_db
    from app.main import app
    from app.models.db_models import Job

    db_gen = app.dependency_overrides[get_db]()
    db = await db_gen.__anext__()
    job = Job(
        title="Account Executive", company_name="Anthropic", apply_url="https://x.com/1"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return profile["id"], job.id


async def test_start_then_status(client):
    profile_id, job_id = await _create_profile_and_job(client)

    start_resp = await client.post(
        "/api/apply/start", json={"profile_id": profile_id, "job_id": job_id}
    )
    assert start_resp.status_code == 200
    application_id = start_resp.json()["application_id"]
    assert start_resp.json()["status"] == "queued"

    status_resp = await client.get(f"/api/apply/status/{application_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["job_title"] == "Account Executive"


async def test_start_with_missing_profile_is_404(client):
    resp = await client.post("/api/apply/start", json={"profile_id": 999, "job_id": 1})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Profile not found"}


async def test_full_pause_resume_cancel_lifecycle(client):
    profile_id, job_id = await _create_profile_and_job(client)
    application_id = (
        await client.post(
            "/api/apply/start", json={"profile_id": profile_id, "job_id": job_id}
        )
    ).json()["application_id"]

    pause_resp = await client.post(f"/api/apply/{application_id}/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "needs_input"

    resume_resp = await client.post(f"/api/apply/{application_id}/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "running"

    cancel_resp = await client.post(f"/api/apply/{application_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Same exact conflict messages the frontend's error handling depends on
    resume_again = await client.post(f"/api/apply/{application_id}/resume")
    assert resume_again.status_code == 409
    assert resume_again.json() == {"detail": "Application is not paused"}

    pause_again = await client.post(f"/api/apply/{application_id}/pause")
    assert pause_again.status_code == 409
    assert pause_again.json() == {"detail": "Application already finished"}
