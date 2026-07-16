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
