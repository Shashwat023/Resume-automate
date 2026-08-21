"""
End-to-end through the real HTTP layer (FastAPI routing, Pydantic
validation, the NotFoundError -> 404 exception handler) — not just the
service in isolation. This is what actually proves the router-thinning
didn't change the contract the frontend depends on.
"""


async def test_create_get_update_round_trip(client):
    created = (
        await client.post(
            "/api/profile",
            json={
                "full_name": "Jordan Smith",
                "email": "j@example.com",
                "phone": "123",
            },
        )
    ).json()
    assert created["full_name"] == "Jordan Smith"
    profile_id = created["id"]

    fetched = await client.get(f"/api/profile/{profile_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "j@example.com"

    updated = await client.put(
        f"/api/profile/{profile_id}", json={"city": "San Francisco"}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["city"] == "San Francisco"
    assert body["full_name"] == "Jordan Smith"  # untouched by the partial update


async def test_get_missing_profile_is_404_with_exact_detail(client):
    resp = await client.get("/api/profile/999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Profile not found"}


async def test_delete_then_get_is_404(client):
    created = (
        await client.post(
            "/api/profile",
            json={
                "full_name": "Jordan Smith",
                "email": "j@example.com",
                "phone": "123",
            },
        )
    ).json()

    delete_resp = await client.delete(f"/api/profile/{created['id']}")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"success": True}

    assert (await client.get(f"/api/profile/{created['id']}")).status_code == 404
