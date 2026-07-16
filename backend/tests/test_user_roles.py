"""Integration tests for admin-only user/role management endpoints."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_assign_role_forbidden_for_non_admin(client, make_user_with_role):
    operator_token = make_user_with_role("operator_user", "operator")
    target_id = client.get(
        "/api/v1/auth/me", headers=_auth_header(operator_token)
    ).json()["id"]

    response = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_name": "admin"},
        headers=_auth_header(operator_token),
    )
    assert response.status_code == 403


def test_assign_role_success_and_idempotent(client, make_user_with_role):
    admin_token = make_user_with_role("admin_user", "admin")
    target_token = make_user_with_role("plain_user")
    target_id = client.get("/api/v1/auth/me", headers=_auth_header(target_token)).json()["id"]

    first = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_name": "operator"},
        headers=_auth_header(admin_token),
    )
    assert first.status_code == 200
    role_names = {r["name"] for r in first.json()["roles"]}
    assert {"viewer", "operator"} <= role_names

    # Assigning the same role again is idempotent, not an error.
    second = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_name": "operator"},
        headers=_auth_header(admin_token),
    )
    assert second.status_code == 200
    assert len(second.json()["roles"]) == len(first.json()["roles"])


def test_assign_nonexistent_role_returns_404(client, make_user_with_role):
    admin_token = make_user_with_role("admin_user", "admin")
    target_token = make_user_with_role("plain_user")
    target_id = client.get("/api/v1/auth/me", headers=_auth_header(target_token)).json()["id"]

    response = client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_name": "superhero"},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROLE_NOT_FOUND"


def test_remove_role_success(client, make_user_with_role):
    admin_token = make_user_with_role("admin_user", "admin")
    target_token = make_user_with_role("plain_user")
    target_id = client.get("/api/v1/auth/me", headers=_auth_header(target_token)).json()["id"]

    client.post(
        f"/api/v1/users/{target_id}/roles",
        json={"role_name": "operator"},
        headers=_auth_header(admin_token),
    )
    response = client.delete(
        f"/api/v1/users/{target_id}/roles/operator", headers=_auth_header(admin_token)
    )
    assert response.status_code == 200
    role_names = {r["name"] for r in response.json()["roles"]}
    assert "operator" not in role_names
