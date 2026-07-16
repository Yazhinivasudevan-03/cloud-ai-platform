"""Integration tests for the read-only AI-output endpoints.

Predictions/anomaly_detections/failure_predictions are never written through
this API (the ml-models batch pipeline owns that), so these tests seed rows
directly via db_session, exactly as the real pipeline's raw SQL inserts would
land them, then verify the GET endpoints serve them correctly.
"""
from datetime import datetime

from app.models.anomaly_detection import AnomalyDetection
from app.models.failure_prediction import FailurePrediction
from app.models.prediction import Prediction


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_deployment(client, token: str) -> dict:
    project = client.post(
        "/api/v1/projects", json={"name": "AI Demo Project"}, headers=_auth_header(token)
    ).json()
    microservice = client.post(
        f"/api/v1/projects/{project['id']}/microservices",
        json={"name": "ai-demo-service"},
        headers=_auth_header(token),
    ).json()
    deployment = client.post(
        f"/api/v1/microservices/{microservice['id']}/deployments",
        json={"name": "ai-demo-deploy"},
        headers=_auth_header(token),
    ).json()
    return deployment


def test_list_predictions_requires_existing_deployment(client, make_user_with_role):
    token = make_user_with_role("viewer_user")
    response = client.get("/api/v1/deployments/999999/predictions", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEPLOYMENT_NOT_FOUND"


def test_list_predictions_returns_seeded_rows_filtered_by_metric_type(
    client, make_user_with_role, db_session
):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    db_session.add_all(
        [
            Prediction(
                deployment_id=deployment["id"],
                model_type="lstm",
                metric_type="cpu_usage_percent",
                predicted_value=72.5,
                confidence_score=0.88,
                target_timestamp=datetime(2026, 7, 15, 13, 0, 0),
                generated_at=datetime(2026, 7, 15, 12, 0, 0),
            ),
            Prediction(
                deployment_id=deployment["id"],
                model_type="lstm",
                metric_type="memory_usage_mb",
                predicted_value=812.3,
                confidence_score=0.91,
                target_timestamp=datetime(2026, 7, 15, 13, 0, 0),
                generated_at=datetime(2026, 7, 15, 12, 0, 0),
            ),
        ]
    )
    db_session.commit()

    viewer_token = make_user_with_role("viewer_user")
    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/predictions",
        params={"metric_type": "cpu_usage_percent"},
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["metric_type"] == "cpu_usage_percent"
    assert body["items"][0]["confidence_score"] == 0.88


def test_list_anomaly_detections_filters_by_is_anomaly(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    db_session.add_all(
        [
            AnomalyDetection(
                deployment_id=deployment["id"],
                metric_type="resource_usage_composite",
                anomaly_score=0.12,
                is_anomaly=False,
                detected_at=datetime(2026, 7, 15, 10, 0, 0),
                details='{"cpu_usage_percent": 40.0}',
            ),
            AnomalyDetection(
                deployment_id=deployment["id"],
                metric_type="resource_usage_composite",
                anomaly_score=0.95,
                is_anomaly=True,
                detected_at=datetime(2026, 7, 15, 11, 0, 0),
                details='{"cpu_usage_percent": 98.0}',
            ),
        ]
    )
    db_session.commit()

    viewer_token = make_user_with_role("viewer_user")
    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/anomaly-detections",
        params={"is_anomaly": "true"},
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["is_anomaly"] is True


def test_list_failure_predictions_returns_seeded_rows(client, make_user_with_role, db_session):
    operator_token = make_user_with_role("operator_user", "operator")
    deployment = _create_deployment(client, operator_token)

    db_session.add(
        FailurePrediction(
            deployment_id=deployment["id"],
            pod_id=None,
            failure_type="deployment_failure",
            probability=0.73,
            predicted_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    viewer_token = make_user_with_role("viewer_user")
    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/failure-predictions",
        headers=_auth_header(viewer_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["probability"] == 0.73
    assert body["items"][0]["failure_type"] == "deployment_failure"
