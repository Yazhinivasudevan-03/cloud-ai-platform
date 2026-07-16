"""Integration tests for the Microservice resource: parent validation, CRUD, RBAC."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token: str, name: str = "Payments Platform") -> dict:
    response = client.post("/api/v1/projects", json={"name": name}, headers=_auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_microservice_requires_existing_project(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/projects/999999/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_create_microservice_success_and_duplicate_conflict(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)

    created = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service", "language": "python"},
        headers=_auth_header(token),
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == project["id"]

    duplicate = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "MICROSERVICE_EXISTS"


def test_list_microservices_filters_by_language(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, token)
    client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service", "language": "python"},
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "frontend-gateway", "language": "typescript"},
        headers=_auth_header(token),
    )

    response = client.get(
        f"/api/v1/projects/{project['id']}/microservices",
        params={"language": "python"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["name"] == "billing-service"


def test_microservice_write_endpoints_forbidden_for_viewer(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, operator_token)
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(operator_token),
    ).json()

    viewer_token = make_user_with_role("viewer_user")
    update_response = client.put(
        f"/api/v1/microservices/{microservice['id']}",
        json={"language": "rust"},
        headers=_auth_header(viewer_token),
    )
    assert update_response.status_code == 403

    delete_response = client.delete(
        f"/api/v1/microservices/{microservice['id']}", headers=_auth_header(viewer_token)
    )
    assert delete_response.status_code == 403


def test_delete_microservice_requires_admin(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    project = _create_project(client, operator_token)
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(operator_token),
    ).json()

    admin_token = make_user_with_role("admin_user", "admin")
    response = client.delete(
        f"/api/v1/microservices/{microservice['id']}", headers=_auth_header(admin_token)
    )
    assert response.status_code == 204
