"""Integration tests for the general (non-account-scoped) timezone
endpoints (Phase 22)."""
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_list_timezones_includes_the_examples_from_the_request(client, make_user_with_role):
    token = make_user_with_role("tz_router_a")
    response = client.get("/api/v1/timezones", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for tz in ("Europe/London", "Asia/Kolkata", "America/New_York", "Asia/Singapore", "Australia/Sydney"):
        assert tz in body


def test_list_timezones_requires_authentication(client):
    response = client.get("/api/v1/timezones")
    assert response.status_code == 401


def test_validate_timezone_accepts_a_real_zone(client, make_user_with_role):
    token = make_user_with_role("tz_router_b")
    response = client.post(
        "/api/v1/timezones/validate", params={"timezone": "Europe/London"}, headers=_auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["utc_offset"] in ("+00:00", "+01:00")
    assert body["current_local_time"] is not None


def test_validate_timezone_rejects_garbage(client, make_user_with_role):
    token = make_user_with_role("tz_router_c")
    response = client.post(
        "/api/v1/timezones/validate", params={"timezone": "Not/A_Real_Zone"}, headers=_auth_header(token)
    )

    assert response.status_code == 200  # a clean structured result, not an error response
    body = response.json()
    assert body["valid"] is False
    assert body["error"] is not None
    assert body["utc_offset"] is None
