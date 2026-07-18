"""Integration tests for the self-service Cloud Provider Account REST API."""
from app.models.cloud_provider_account import CloudProviderAccount


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    payload = {
        "provider": "aws",
        "account_name": "prod-aws",
        "region": "us-east-1",
        "account_identifier": "123456789012",
        "credentials": {"access_key_id": "AKIA_FAKE", "secret_access_key": "fake-secret"},
    }
    payload.update(overrides)
    return payload


def test_create_cloud_provider_account_succeeds_and_hides_credentials(client, make_user_with_role):
    token = make_user_with_role("cloud_user_a")
    response = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "aws"
    assert body["account_name"] == "prod-aws"
    assert body["region"] == "us-east-1"
    assert body["account_identifier"] == "123456789012"
    assert body["is_active"] is True
    assert "credentials" not in body
    assert "credentials_encrypted" not in body


def test_create_cloud_provider_account_accepts_any_provider_name(client, make_user_with_role):
    token = make_user_with_role("cloud_user_b")
    response = client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(provider="my-custom-cloud", account_name="custom-1", region="eu-west-2"),
        headers=_auth_header(token),
    )
    assert response.status_code == 201
    assert response.json()["provider"] == "my-custom-cloud"


def test_duplicate_account_name_for_same_user_rejected(client, make_user_with_role):
    token = make_user_with_role("cloud_user_c")
    client.post("/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token))
    response = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_NAME_EXISTS"


def test_same_account_name_allowed_for_different_users(client, make_user_with_role):
    token_a = make_user_with_role("cloud_user_d")
    token_b = make_user_with_role("cloud_user_e")
    resp_a = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token_a)
    )
    resp_b = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token_b)
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201


def test_list_only_returns_own_accounts(client, make_user_with_role):
    token_a = make_user_with_role("cloud_user_f")
    token_b = make_user_with_role("cloud_user_g")
    client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(account_name="a-account"),
        headers=_auth_header(token_a),
    )
    client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(account_name="b-account"),
        headers=_auth_header(token_b),
    )

    response = client.get("/api/v1/cloud-provider-accounts", headers=_auth_header(token_a))
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["account_name"] == "a-account"


def test_filter_by_provider(client, make_user_with_role):
    token = make_user_with_role("cloud_user_h")
    client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(provider="aws", account_name="aws-1"),
        headers=_auth_header(token),
    )
    client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(provider="azure", account_name="azure-1", region="eastus"),
        headers=_auth_header(token),
    )

    response = client.get(
        "/api/v1/cloud-provider-accounts",
        params={"provider": "azure"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["account_name"] == "azure-1"


def test_no_restriction_on_account_count(client, make_user_with_role):
    token = make_user_with_role("cloud_user_i")
    for i in range(15):
        response = client.post(
            "/api/v1/cloud-provider-accounts",
            json=_payload(account_name=f"account-{i}", region=f"region-{i}"),
            headers=_auth_header(token),
        )
        assert response.status_code == 201

    response = client.get(
        "/api/v1/cloud-provider-accounts", params={"page_size": 100}, headers=_auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 15


def test_get_own_account(client, make_user_with_role):
    token = make_user_with_role("cloud_user_j")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token)
    ).json()

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{created['id']}", headers=_auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["account_name"] == "prod-aws"


def test_cannot_get_another_users_account(client, make_user_with_role):
    token_a = make_user_with_role("cloud_user_k")
    token_b = make_user_with_role("cloud_user_l")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token_a)
    ).json()

    response = client.get(
        f"/api/v1/cloud-provider-accounts/{created['id']}", headers=_auth_header(token_b)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_get_nonexistent_account_returns_404(client, make_user_with_role):
    token = make_user_with_role("cloud_user_m")
    response = client.get("/api/v1/cloud-provider-accounts/999999", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_NOT_FOUND"


def test_update_own_account_region_and_credentials(client, make_user_with_role, db_session):
    token = make_user_with_role("cloud_user_n")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token)
    ).json()

    old_row = db_session.get(CloudProviderAccount, created["id"])
    old_encrypted = old_row.credentials_encrypted

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{created['id']}",
        json={"region": "ap-southeast-2", "credentials": {"access_key_id": "NEW", "secret_access_key": "NEW"}},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["region"] == "ap-southeast-2"

    db_session.expire_all()
    new_row = db_session.get(CloudProviderAccount, created["id"])
    assert new_row.credentials_encrypted != old_encrypted


def test_cannot_update_another_users_account(client, make_user_with_role):
    token_a = make_user_with_role("cloud_user_o")
    token_b = make_user_with_role("cloud_user_p")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token_a)
    ).json()

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{created['id']}",
        json={"region": "eu-west-1"},
        headers=_auth_header(token_b),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_update_rejects_renaming_to_an_existing_account_name(client, make_user_with_role):
    token = make_user_with_role("cloud_user_q")
    client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(account_name="first"),
        headers=_auth_header(token),
    )
    second = client.post(
        "/api/v1/cloud-provider-accounts",
        json=_payload(account_name="second"),
        headers=_auth_header(token),
    ).json()

    response = client.put(
        f"/api/v1/cloud-provider-accounts/{second['id']}",
        json={"account_name": "first"},
        headers=_auth_header(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CLOUD_ACCOUNT_NAME_EXISTS"


def test_delete_own_account(client, make_user_with_role):
    token = make_user_with_role("cloud_user_r")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token)
    ).json()

    response = client.delete(
        f"/api/v1/cloud-provider-accounts/{created['id']}", headers=_auth_header(token)
    )
    assert response.status_code == 204

    get_response = client.get(
        f"/api/v1/cloud-provider-accounts/{created['id']}", headers=_auth_header(token)
    )
    assert get_response.status_code == 404


def test_cannot_delete_another_users_account(client, make_user_with_role):
    token_a = make_user_with_role("cloud_user_s")
    token_b = make_user_with_role("cloud_user_t")
    created = client.post(
        "/api/v1/cloud-provider-accounts", json=_payload(), headers=_auth_header(token_a)
    ).json()

    response = client.delete(
        f"/api/v1/cloud-provider-accounts/{created['id']}", headers=_auth_header(token_b)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"
