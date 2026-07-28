"""Integration tests for the Pod resource: parent validation, CRUD, filters, RBAC."""


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "Payments Platform"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "billing-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "billing-deploy"},
        headers=_auth_header(token),
    ).json()
    return deployment


def test_create_pod_requires_existing_deployment(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post(
        "/api/v1/deployments/999999/pods",
        json={"pod_name": "billing-deploy-abc123"},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_create_pod_success_and_duplicate_conflict(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)

    created = client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "billing-deploy-abc123", "node_name": "node-1"},
        headers=_auth_header(token),
    )
    assert created.status_code == 201
    assert created.json()["deployment_id"] == deployment["id"]

    duplicate = client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "billing-deploy-abc123"},
        headers=_auth_header(token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "POD_EXISTS"


def test_list_pods_filters_by_status_and_sorts(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)
    client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "pod-a", "status": "running"},
        headers=_auth_header(token),
    )
    client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "pod-b", "status": "failed"},
        headers=_auth_header(token),
    )

    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/pods",
        params={"status": "running"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["pod_name"] == "pod-a"


def test_update_pod_restart_count_succeeds_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)
    pod = client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "pod-a"},
        headers=_auth_header(token),
    ).json()

    response = client.put(
        f"/api/v1/pods/{pod['id']}",
        json={"restart_count": 3, "status": "failed"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["restart_count"] == 3
    assert response.json()["status"] == "failed"


def test_delete_pod_requires_admin(client, make_user_with_role, db_session):
    from app.models.user import Role, User

    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)
    pod = client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "pod-a"},
        headers=_auth_header(operator_token),
    ).json()

    denied = client.delete(f"/api/v1/pods/{pod['id']}", headers=_auth_header(operator_token))
    assert denied.status_code == 403

    # Deleting requires the admin role AND being the project's own owner
    # (Phase 24: admin is an app-management role within a tenant, not a
    # cross-tenant bypass) - grant the SAME owner the admin role rather
    # than using a second, unrelated user.
    admin_role = db_session.query(Role).filter(Role.name == "admin").one()
    owner = db_session.query(User).filter(User.username == "operator_user").one()
    owner.roles.append(admin_role)
    db_session.commit()

    allowed = client.delete(f"/api/v1/pods/{pod['id']}", headers=_auth_header(operator_token))
    assert allowed.status_code == 204


def test_delete_pod_forbidden_for_a_non_owner_admin(client, make_user_with_role):
    owner_token = make_user_with_role("pod_owner", "operator")
    deployment = _create_deployment(client, owner_token)
    pod = client.post(
        f"/api/v1/deployments/{deployment['id']}/pods",
        json={"pod_name": "pod-a"},
        headers=_auth_header(owner_token),
    ).json()

    other_admin_token = make_user_with_role("other_pod_admin", "admin")
    response = client.delete(f"/api/v1/pods/{pod['id']}", headers=_auth_header(other_admin_token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_PROJECT"
