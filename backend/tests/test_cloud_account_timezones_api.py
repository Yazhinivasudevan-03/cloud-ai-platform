"""Integration tests for the per-cloud-account multi-timezone API (Phase
22). Ownership-checked like alert thresholds - only the account's own
owner may manage its timezone entries."""
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_account(client, token, account_name="tz-account") -> int:
    response = client.post(
        "/api/v1/cloud-provider-accounts",
        json={
            "provider": "aws",
            "account_name": account_name,
            "region": "us-east-1",
            "credentials": {"access_key_id": "x", "secret_access_key": "y"},
        },
        headers=_auth_header(token),
    )
    return response.json()["id"]


def test_list_timezones_is_empty_for_a_fresh_account(client, make_user_with_role):
    token = make_user_with_role("tz_user_a")
    account_id = _create_account(client, token)

    response = client.get(f"/api/v1/cloud-provider-accounts/{account_id}/timezones", headers=_auth_header(token))

    assert response.status_code == 200
    assert response.json() == []


def test_create_timezone_entry_computes_provider_and_offset(client, make_user_with_role):
    token = make_user_with_role("tz_user_b")
    account_id = _create_account(client, token)

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "eu-west-2", "label": "London Production", "timezone": "Europe/London"},
        headers=_auth_header(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "aws"  # derived from the account, not stored redundantly
    assert body["region"] == "eu-west-2"
    assert body["timezone"] == "Europe/London"
    assert body["utc_offset"] in ("+00:00", "+01:00")  # GMT or BST depending on when the test runs
    assert "current_local_time" in body


def test_create_multiple_regions_on_the_same_account(client, make_user_with_role):
    """The actual point of this feature: one account, multiple
    region/timezone entries - an AWS account with both London and Mumbai
    deployments."""
    token = make_user_with_role("tz_user_c")
    account_id = _create_account(client, token)

    client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "eu-west-2", "label": "London", "timezone": "Europe/London"},
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "ap-south-1", "label": "Mumbai", "timezone": "Asia/Kolkata"},
        headers=_auth_header(token),
    )

    response = client.get(f"/api/v1/cloud-provider-accounts/{account_id}/timezones", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    regions = {entry["region"] for entry in body}
    assert regions == {"eu-west-2", "ap-south-1"}
    mumbai = next(e for e in body if e["region"] == "ap-south-1")
    assert mumbai["utc_offset"] == "+05:30"


def test_create_rejects_invalid_iana_timezone(client, make_user_with_role):
    token = make_user_with_role("tz_user_d")
    account_id = _create_account(client, token)

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "eu-west-2", "label": "London", "timezone": "Not/A_Real_Zone"},
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TIMEZONE"


def test_create_rejects_duplicate_region_and_timezone(client, make_user_with_role):
    token = make_user_with_role("tz_user_e")
    account_id = _create_account(client, token)
    payload = {"region": "eu-west-2", "label": "London", "timezone": "Europe/London"}

    client.post(f"/api/v1/cloud-provider-accounts/{account_id}/timezones", json=payload, headers=_auth_header(token))
    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones", json=payload, headers=_auth_header(token)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_TIMEZONE_EXISTS"


def test_update_timezone_entry(client, make_user_with_role):
    token = make_user_with_role("tz_user_f")
    account_id = _create_account(client, token)
    create_response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "eu-west-2", "label": "London", "timezone": "Europe/London"},
        headers=_auth_header(token),
    )
    timezone_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones/{timezone_id}",
        json={"label": "London Production (renamed)", "availability_zone": "eu-west-2a"},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "London Production (renamed)"
    assert body["availability_zone"] == "eu-west-2a"
    assert body["timezone"] == "Europe/London"  # untouched


def test_delete_timezone_entry(client, make_user_with_role):
    token = make_user_with_role("tz_user_g")
    account_id = _create_account(client, token)
    create_response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": "eu-west-2", "label": "London", "timezone": "Europe/London"},
        headers=_auth_header(token),
    )
    timezone_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones/{timezone_id}", headers=_auth_header(token)
    )
    assert delete_response.status_code == 204

    list_response = client.get(f"/api/v1/cloud-provider-accounts/{account_id}/timezones", headers=_auth_header(token))
    assert list_response.json() == []


def test_cannot_manage_another_users_account_timezones(client, make_user_with_role):
    token_a = make_user_with_role("tz_user_h")
    token_b = make_user_with_role("tz_user_i")
    account_id = _create_account(client, token_a)

    response = client.get(f"/api/v1/cloud-provider-accounts/{account_id}/timezones", headers=_auth_header(token_b))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_timezones_for_nonexistent_account_returns_404(client, make_user_with_role):
    token = make_user_with_role("tz_user_j")
    response = client.get("/api/v1/cloud-provider-accounts/999999/timezones", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_NOT_FOUND"
