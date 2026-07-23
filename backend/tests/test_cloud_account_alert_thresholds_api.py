"""Integration tests for the per-cloud-account CPU/memory/disk/network
alert threshold API (Phase 20-21)."""
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_account(client, token) -> int:
    response = client.post(
        "/api/v1/cloud-provider-accounts",
        json={
            "provider": "aws",
            "account_name": "threshold-account",
            "region": "us-east-1",
            "credentials": {"access_key_id": "x", "secret_access_key": "y"},
        },
        headers=_auth_header(token),
    )
    return response.json()["id"]


def test_get_thresholds_returns_platform_defaults_when_never_configured(client, make_user_with_role):
    token = make_user_with_role("threshold_user_a")
    account_id = _create_account(client, token)

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account_id}/alert-thresholds", headers=_auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cpu_warning_threshold"] is None  # no override set
    assert body["effective_cpu_warning_threshold"] == 60.0  # platform default
    assert body["effective_cpu_critical_threshold"] == 80.0
    assert body["effective_cpu_saturated_threshold"] == 100.0
    assert body["effective_memory_warning_threshold"] == 60.0
    assert body["effective_memory_critical_threshold"] == 80.0
    assert body["effective_memory_saturated_threshold"] == 90.0
    assert body["effective_disk_warning_threshold"] == 60.0
    assert body["effective_disk_critical_threshold"] == 80.0
    assert body["effective_disk_saturated_threshold"] == 90.0
    assert body["effective_network_warning_threshold"] == 60.0
    assert body["effective_network_critical_threshold"] == 80.0
    assert body["effective_network_saturated_threshold"] == 90.0


def test_update_disk_and_network_thresholds(client, make_user_with_role):
    token = make_user_with_role("threshold_user_g")
    account_id = _create_account(client, token)

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{account_id}/alert-thresholds",
        json={"disk_warning_threshold": 50.0, "network_saturated_threshold": 95.0},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_disk_warning_threshold"] == 50.0
    assert body["effective_disk_critical_threshold"] == 80.0  # untouched
    assert body["effective_network_saturated_threshold"] == 95.0
    assert body["effective_network_warning_threshold"] == 60.0  # untouched


def test_update_thresholds_persists_override_and_reports_it_as_effective(client, make_user_with_role):
    token = make_user_with_role("threshold_user_b")
    account_id = _create_account(client, token)

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{account_id}/alert-thresholds",
        json={"cpu_warning_threshold": 40.0, "cpu_critical_threshold": 65.0},
        headers=_auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cpu_warning_threshold"] == 40.0
    assert body["effective_cpu_warning_threshold"] == 40.0
    assert body["effective_cpu_critical_threshold"] == 65.0
    assert body["effective_cpu_saturated_threshold"] == 100.0  # untouched - still platform default


def test_update_thresholds_rejects_non_ascending_tiers(client, make_user_with_role):
    token = make_user_with_role("threshold_user_c")
    account_id = _create_account(client, token)

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{account_id}/alert-thresholds",
        json={"cpu_warning_threshold": 90.0},  # above the default critical (80) - would break ordering
        headers=_auth_header(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_THRESHOLD_ORDERING"


def test_cannot_view_another_users_account_thresholds(client, make_user_with_role):
    token_a = make_user_with_role("threshold_user_d")
    token_b = make_user_with_role("threshold_user_e")
    account_id = _create_account(client, token_a)

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{account_id}/alert-thresholds", headers=_auth_header(token_b)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_thresholds_for_nonexistent_account_returns_404(client, make_user_with_role):
    token = make_user_with_role("threshold_user_f")
    response = client.get(
        "/api/v1/cloud-provider-accounts/999999/alert-thresholds", headers=_auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_NOT_FOUND"
