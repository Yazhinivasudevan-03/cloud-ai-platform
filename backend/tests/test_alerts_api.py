"""Integration tests for the Alert REST API."""
from datetime import datetime

from app.models.alert import Alert


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "Alerts API Demo"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "alerts-api-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "alerts-api-deploy"},
        headers=_auth_header(token),
    ).json()
    return deployment


def test_evaluate_alerts_forbidden_for_viewer(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.post("/api/v1/alerts/evaluate", headers=_auth_header(token))
    assert response.status_code == 403


def test_evaluate_alerts_returns_summary_for_operator(client, make_user_with_role):
    token = make_user_with_role("operator_user", "operator")
    response = client.post("/api/v1/alerts/evaluate", headers=_auth_header(token))
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "deployments_evaluated",
        "alerts_created",
        "alerts_resolved",
        "notifications_sent",
    }


def test_list_alerts_requires_existing_deployment(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get("/api/v1/deployments/999999/alerts", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_list_and_get_alerts(client, make_user_with_role, db_session):
    token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, token)

    db_session.add(
        Alert(
            deployment_id=deployment["id"],
            alert_type="cpu_elevated",
            severity="warning",
            threshold_percent=60.0,
            message="CPU usage at 65.0% - above warning threshold",
            status="active",
            triggered_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    viewer_token = make_user_with_role("viewer_user")
    list_response = client.get(
        f"/api/v1/deployments/{deployment['id']}/alerts",
        params={"severity": "warning"},
        headers=_auth_header(viewer_token),
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["meta"]["total"] == 1
    alert_id = body["items"][0]["id"]

    get_response = client.get(f"/api/v1/alerts/{alert_id}", headers=_auth_header(viewer_token))
    assert get_response.status_code == 200
    assert get_response.json()["alert_type"] == "cpu_elevated"


def test_get_alert_not_found(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get("/api/v1/alerts/999999", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ALERT_NOT_FOUND"


def test_update_alert_forbidden_for_viewer(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)
    alert = Alert(
        deployment_id=deployment["id"],
        alert_type="cpu_elevated",
        severity="warning",
        threshold_percent=60.0,
        message="test",
        status="active",
        triggered_at=datetime(2026, 7, 15, 12, 0, 0),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    viewer_token = make_user_with_role("viewer_user")
    response = client.patch(
        f"/api/v1/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 403


def test_acknowledge_then_resolve_alert(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)
    alert = Alert(
        deployment_id=deployment["id"],
        alert_type="cpu_elevated",
        severity="warning",
        threshold_percent=60.0,
        message="test",
        status="active",
        triggered_at=datetime(2026, 7, 15, 12, 0, 0),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    ack_response = client.patch(
        f"/api/v1/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers=_auth_header(operator_token),
    )
    assert ack_response.status_code == 200
    assert ack_response.json()["status"] == "acknowledged"

    resolve_response = client.patch(
        f"/api/v1/alerts/{alert.id}",
        json={"status": "resolved"},
        headers=_auth_header(operator_token),
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"
    assert resolve_response.json()["resolved_at"] is not None


def test_invalid_status_transition_rejected(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)
    alert = Alert(
        deployment_id=deployment["id"],
        alert_type="cpu_elevated",
        severity="warning",
        threshold_percent=60.0,
        message="test",
        status="resolved",
        triggered_at=datetime(2026, 7, 15, 12, 0, 0),
        resolved_at=datetime(2026, 7, 15, 13, 0, 0),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    response = client.patch(
        f"/api/v1/alerts/{alert.id}",
        json={"status": "acknowledged"},
        headers=_auth_header(operator_token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_ALERT_TRANSITION"
