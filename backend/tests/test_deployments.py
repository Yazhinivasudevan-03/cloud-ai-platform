"""Integration tests for the Deployment resource: parent validation, CRUD, filters, RBAC."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_microservice(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(token),
    ).json()
    return microservice


def test_deployment_is_forbidden_for_a_non_owner(client, make_user_with_role):
    owner_token = make_user_with_role("deployment_owner", "operator")
    microservice = _create_microservice(client, owner_token)
    created = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "production"},
        headers=_auth_header(owner_token),
    ).json()

    other_token = make_user_with_role("deployment_other", "admin")
    get_response = client.get(
        f"/api/v1/deployments/{created['id']}", headers=_auth_header(other_token)
    )
    assert get_response.status_code == 403
    assert get_response.json()["error"]["code"] == "NOT_YOUR_PROJECT"

    delete_response = client.delete(
        f"/api/v1/deployments/{created['id']}", headers=_auth_header(other_token)
    )
    assert delete_response.status_code == 403
    assert delete_response.json()["error"]["code"] == "NOT_YOUR_PROJECT"

    list_response = client.get(
        f"/api/v1/microservices/{microservice['id']}/deployments", headers=_auth_header(other_token)
    )
    assert list_response.status_code == 403


def test_create_deployment_requires_existing_microservice(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/microservices/999999/deployments",
        json={"name": "billing-deploy"},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MICROSERVICE_NOT_FOUND"


def test_create_deployment_success_and_namespace_conflict(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)

    created = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "production", "replicas": 3},
        headers=_auth_header(token),
    )
    assert created.status_code == 201
    assert created.json()["status"] == "unknown"
    assert created.json()["replicas"] == 3

    duplicate = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "production"},
        headers=_auth_header(token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DEPLOYMENT_EXISTS"

    # Same name in a different namespace is allowed.
    different_namespace = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "staging"},
        headers=_auth_header(token),
    )
    assert different_namespace.status_code == 201


def test_list_deployments_filters_by_status(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "production", "status": "running"},
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "namespace": "staging", "status": "failed"},
        headers=_auth_header(token),
    )

    response = client.get(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        params={"status": "failed"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["namespace"] == "staging"


def test_list_deployments_filters_by_cloud_provider_account_id(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    account_a = _create_cloud_account(client, token, "account-a")
    account_b = _create_cloud_account(client, token, "account-b")

    client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={
            "name": "svc-a",
            "namespace": "production",
            "cloud_provider_account_id": account_a,
        },
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={
            "name": "svc-b",
            "namespace": "production",
            "cloud_provider_account_id": account_b,
        },
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "svc-unlinked", "namespace": "production"},
        headers=_auth_header(token),
    )

    response = client.get(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        params={"cloud_provider_account_id": account_a},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["name"] == "svc-a"


def test_update_deployment_status_succeeds_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy"},
        headers=_auth_header(token),
    ).json()

    response = client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"status": "running", "replicas": 5},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["replicas"] == 5


def test_invalid_status_value_rejected(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    response = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "status": "not-a-real-status"},
        headers=_auth_header(token),
    )
    assert response.status_code == 422


def _create_cloud_account(client, token: str, account_name: str = "deploy-tz-account") -> int:
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


def _create_account_timezone(client, token: str, account_id: int, region: str, timezone: str) -> int:
    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account_id}/timezones",
        json={"region": region, "label": region, "timezone": timezone},
        headers=_auth_header(token),
    )
    return response.json()["id"]


def test_create_deployment_with_cloud_account_timezone(client, make_user_with_role):
    """Phase 22: a deployment may optionally link to one of its own cloud
    account's configured (region, timezone) entries."""
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    account_id = _create_cloud_account(client, token)
    timezone_id = _create_account_timezone(client, token, account_id, "eu-west-2", "Europe/London")

    response = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={
            "name": "billing-deploy",
            "cloud_provider_account_id": account_id,
            "cloud_account_timezone_id": timezone_id,
        },
        headers=_auth_header(token),
    )
    assert response.status_code == 201
    assert response.json()["cloud_account_timezone_id"] == timezone_id


def test_create_deployment_rejects_timezone_from_a_different_account(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    account_id = _create_cloud_account(client, token, "account-a")
    other_account_id = _create_cloud_account(client, token, "account-b")
    timezone_id = _create_account_timezone(client, token, other_account_id, "ap-south-1", "Asia/Kolkata")

    response = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={
            "name": "billing-deploy",
            "cloud_provider_account_id": account_id,
            "cloud_account_timezone_id": timezone_id,
        },
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TIMEZONE_ACCOUNT_MISMATCH"


def test_update_deployment_to_add_a_cloud_account_timezone(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    account_id = _create_cloud_account(client, token)
    timezone_id = _create_account_timezone(client, token, account_id, "ap-south-1", "Asia/Kolkata")
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "cloud_provider_account_id": account_id},
        headers=_auth_header(token),
    ).json()

    response = client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_account_timezone_id": timezone_id},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["cloud_account_timezone_id"] == timezone_id


def test_update_deployment_rejects_timezone_not_belonging_to_its_own_account(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    microservice = _create_microservice(client, token)
    account_id = _create_cloud_account(client, token, "account-c")
    other_account_id = _create_cloud_account(client, token, "account-d")
    timezone_id = _create_account_timezone(client, token, other_account_id, "eu-west-2", "Europe/London")
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy", "cloud_provider_account_id": account_id},
        headers=_auth_header(token),
    ).json()

    response = client.put(
        f"/api/v1/deployments/{deployment['id']}",
        json={"cloud_account_timezone_id": timezone_id},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TIMEZONE_ACCOUNT_MISMATCH"
