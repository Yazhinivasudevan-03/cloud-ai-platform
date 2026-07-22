"""Tests for AuditLogMiddleware - confirms the AuditLog table (previously
modeled but never populated by any code path) now actually receives a row
for every mutating request, with the correct acting user, action, entity
type/id, and outcome status."""
from app.models.audit_log import AuditLog


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_request_does_not_create_an_audit_log_row(client, make_user_with_role, db_session):
    token = make_user_with_role("audit_viewer_a")
    before = db_session.query(AuditLog).count()

    client.get("/api/v1/auth/me", headers=_auth_header(token))

    assert db_session.query(AuditLog).count() == before


def test_post_request_creates_audit_log_row_with_correct_user_and_entity(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("audit_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()

    response = client.post(
        "/api/v1/projects", json={"name": "audit-test-project"}, headers=_auth_header(token)
    )
    assert response.status_code == 201

    db_session.expire_all()
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "POST /api/v1/projects")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.user_id == me["id"]
    assert row.entity_type == "projects"
    assert "status=201" in row.details


def test_put_request_captures_entity_id_from_path(client, make_user_with_role, db_session):
    token = make_user_with_role("audit_op_b", "operator")
    project = client.post(
        "/api/v1/projects", json={"name": "audit-test-project-2"}, headers=_auth_header(token)
    ).json()

    response = client.put(
        f"/api/v1/projects/{project['id']}",
        json={"description": "updated"},
        headers=_auth_header(token),
    )
    assert response.status_code == 200

    db_session.expire_all()
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == f"PUT /api/v1/projects/{project['id']}")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.entity_type == "projects"
    assert row.entity_id == project["id"]


def test_denied_mutation_is_still_logged(client, make_user_with_role, db_session):
    """A viewer lacks operator/admin, so this create is rejected (403) - a
    denied mutation attempt is genuinely audit-worthy, arguably more so
    than a routine success, so it must still be recorded."""
    token = make_user_with_role("audit_viewer_b")

    response = client.post(
        "/api/v1/projects", json={"name": "should-be-denied"}, headers=_auth_header(token)
    )
    assert response.status_code == 403

    db_session.expire_all()
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "POST /api/v1/projects")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert "status=403" in row.details


def test_unauthenticated_mutation_logs_with_null_user(client, db_session):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "audit_register_test",
            "email": "audit_register_test@example.com",
            "password": "Sup3rSecret1",
            "full_name": "Audit Register Test",
        },
    )
    assert response.status_code == 201

    db_session.expire_all()
    row = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "POST /api/v1/auth/register")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.user_id is None
    assert row.entity_type == "auth"
