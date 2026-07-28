"""Integration tests for the Project resource: CRUD, pagination/filter/sort, RBAC."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_project_forbidden_for_viewer(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


def test_create_project_succeeds_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/projects",
        json={"name": "Payments Platform", "description": "Core payments infra"},
        headers=_auth_header(token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Payments Platform"
    assert body["owner_id"] is not None


def test_create_project_rejects_duplicate_name(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    client.post("/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token))
    response = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_EXISTS"


def test_get_project_not_found(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get("/api/v1/projects/999999", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_list_projects_pagination_and_name_filter(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    for name in ["Alpha Service", "Beta Service", "Gamma Analytics"]:
        client.post("/api/v1/projects", json={"name": name}, headers=_auth_header(token))

    response = client.get(
        "/api/v1/projects",
        params={"name": "service", "page": 1, "page_size": 1, "sort_by": "name", "order": "asc"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 2
    assert body["meta"]["total_pages"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Alpha Service"


def test_update_project_forbidden_for_viewer(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    created = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(operator_token)
    ).json()

    viewer_token = make_user_with_role("viewer_user")
    response = client.put(
        f"/api/v1/projects/{created['id']}",
        json={"description": "hijack attempt"},
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 403


def test_update_project_succeeds_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    created = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    ).json()

    response = client.put(
        f"/api/v1/projects/{created['id']}",
        json={"description": "Updated description"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"


def test_delete_project_requires_admin(client, make_user_with_role, db_session):
    from app.models.user import Role, User

    operator_token = make_user_with_role("operator_user", "operator")
    created = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(operator_token)
    ).json()

    denied = client.delete(
        f"/api/v1/projects/{created['id']}", headers=_auth_header(operator_token)
    )
    assert denied.status_code == 403

    # Deleting requires the admin role AND being the project's own owner
    # (Phase 24: admin is an app-management role within a tenant, not a
    # cross-tenant bypass - see test_delete_project_forbidden_for_a_non_owner_admin
    # below) - grant the SAME owner the admin role too, rather than using
    # a second, unrelated user.
    admin_role = db_session.query(Role).filter(Role.name == "admin").one()
    owner = db_session.query(User).filter(User.username == "operator_user").one()
    owner.roles.append(admin_role)
    db_session.commit()

    allowed = client.delete(
        f"/api/v1/projects/{created['id']}", headers=_auth_header(operator_token)
    )
    assert allowed.status_code == 204

    missing = client.get(
        f"/api/v1/projects/{created['id']}", headers=_auth_header(operator_token)
    )
    assert missing.status_code == 404


def test_delete_project_forbidden_for_a_non_owner_admin(client, make_user_with_role):
    """Phase 24: admin is an app-management role within a tenant, not a
    cross-tenant data-access bypass - only a platform is_superuser can act
    on another user's project."""
    owner_token = make_user_with_role("project_owner", "operator")
    created = client.post(
        "/api/v1/projects", json={"name": "Someone Else's Project"}, headers=_auth_header(owner_token)
    ).json()

    other_admin_token = make_user_with_role("other_admin", "admin")
    response = client.delete(
        f"/api/v1/projects/{created['id']}", headers=_auth_header(other_admin_token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_PROJECT"


def test_get_and_list_projects_are_isolated_per_owner(client, make_user_with_role):
    user_a_token = make_user_with_role("project_user_a", "operator")
    user_b_token = make_user_with_role("project_user_b", "operator")

    created = client.post(
        "/api/v1/projects", json={"name": "User A's Private Project"}, headers=_auth_header(user_a_token)
    ).json()

    get_response = client.get(
        f"/api/v1/projects/{created['id']}", headers=_auth_header(user_b_token)
    )
    assert get_response.status_code == 403
    assert get_response.json()["error"]["code"] == "NOT_YOUR_PROJECT"

    list_response = client.get("/api/v1/projects", headers=_auth_header(user_b_token))
    assert list_response.status_code == 200
    assert all(item["id"] != created["id"] for item in list_response.json()["items"])

    own_list_response = client.get("/api/v1/projects", headers=_auth_header(user_a_token))
    assert any(item["id"] == created["id"] for item in own_list_response.json()["items"])
