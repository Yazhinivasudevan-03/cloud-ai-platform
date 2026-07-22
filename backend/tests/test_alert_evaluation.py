"""Tests for the AlertEvaluationService rule engine, exercised directly
against the DB (not through the HTTP API) since it's triggered by the
scheduler/POST /alerts/evaluate, not by a request body.
"""
from datetime import datetime

import pytest

from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.microservice import Microservice
from app.models.notification import Notification
from app.models.project import Project
from app.models.resource_usage import ResourceUsage
from app.models.user import Role, User
from app.services.alert_evaluation_service import AlertEvaluationService


@pytest.fixture()
def demo_deployment(db_session):
    owner = User(
        username="alert_owner",
        email="alert_owner@example.com",
        full_name="Alert Owner",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()

    project = Project(name="Alerting Demo", owner_id=owner.id)
    db_session.add(project)
    db_session.flush()

    microservice = Microservice(project_id=project.id, name="alert-service")
    db_session.add(microservice)
    db_session.flush()

    deployment = Deployment(microservice_id=microservice.id, name="alert-deploy")
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)
    return deployment


@pytest.fixture()
def admin_user(db_session):
    admin_role = db_session.query(Role).filter(Role.name == "admin").one()
    user = User(
        username="alert_admin",
        email="alert_admin@example.com",
        full_name="Alert Admin",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
    )
    user.roles.append(admin_role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _add_resource_usage(db_session, deployment_id: int, cpu_usage_percent: float):
    db_session.add(
        ResourceUsage(
            deployment_id=deployment_id,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_mb=500.0,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()


def test_cpu_warning_threshold_creates_alert_and_notifies_admin(
    db_session, demo_deployment, admin_user
):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)

    summary = AlertEvaluationService(db_session).evaluate_all()

    assert summary["alerts_created"] == 1
    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_type == "cpu_elevated"
    assert alert.severity == "warning"
    assert alert.status == "active"

    notifications = db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == admin_user.id
    assert notifications[0].channel == "dashboard"


def test_alert_notifies_admin_via_sms_when_twilio_configured_and_phone_number_set(
    db_session, demo_deployment, admin_user, monkeypatch
):
    """Proves the SMS channel (Phase 19) is genuinely wired into the same
    fan-out every other channel goes through, not just unit-tested in
    isolation - an admin with a phone_number on file gets a real "sms"
    Notification row once Twilio is configured, mirroring how the
    pre-existing "dashboard" channel test above proves the base wiring."""
    from unittest.mock import MagicMock, patch

    from app.config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")
    admin_user.phone_number = "+14155552671"
    db_session.commit()

    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.sms_notifier.httpx.post", return_value=mock_response) as mock_post:
        AlertEvaluationService(db_session).evaluate_all()

    mock_post.assert_called_once()
    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    channels = {
        n.channel
        for n in db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    }
    assert "sms" in channels


def test_cpu_saturated_uses_highest_tier(db_session, demo_deployment, admin_user):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=100.0)

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_type == "cpu_saturated"
    assert alert.severity == "critical"
    assert alert.threshold_percent == 100.0


@pytest.mark.parametrize(
    "cpu_usage_percent,expected_type,expected_severity",
    [
        (59.9, None, None),  # just below the warning tier - no alert at all
        (60.0, "cpu_elevated", "warning"),  # exact warning boundary (inclusive)
        (79.9, "cpu_elevated", "warning"),  # just below the critical tier
        (80.0, "cpu_high", "critical"),  # exact critical boundary (inclusive)
        (99.9, "cpu_high", "critical"),  # just below the saturated tier
        (100.0, "cpu_saturated", "critical"),  # exact saturated boundary (inclusive)
    ],
)
def test_cpu_threshold_boundaries_are_inclusive(
    db_session, demo_deployment, admin_user, cpu_usage_percent, expected_type, expected_severity
):
    """ALERT_CPU_WARNING/CRITICAL/SATURATED_THRESHOLD default to 60/80/100 -
    verifies the >= comparisons in _cpu_condition() land on the correct tier
    at the exact boundary value, not just comfortably inside each band."""
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=cpu_usage_percent)

    summary = AlertEvaluationService(db_session).evaluate_all()

    if expected_type is None:
        assert summary["alerts_created"] == 0
        return

    assert summary["alerts_created"] == 1
    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_type == expected_type
    assert alert.severity == expected_severity

    notifications = db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    assert len(notifications) == 1
    assert notifications[0].user_id == admin_user.id


def test_severity_escalation_resolves_old_alert_and_creates_new_one(
    db_session, demo_deployment, admin_user
):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)
    service = AlertEvaluationService(db_session)
    service.evaluate_all()

    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=85.0)
    summary = service.evaluate_all()

    assert summary["alerts_created"] == 1
    assert summary["alerts_resolved"] == 1

    alerts = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).all()
    assert len(alerts) == 2
    resolved = [a for a in alerts if a.status == "resolved"]
    active = [a for a in alerts if a.status == "active"]
    assert resolved[0].alert_type == "cpu_elevated"
    assert active[0].alert_type == "cpu_high"


def test_condition_clearing_resolves_alert_without_creating_new_one(
    db_session, demo_deployment, admin_user
):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)
    service = AlertEvaluationService(db_session)
    service.evaluate_all()

    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=20.0)
    summary = service.evaluate_all()

    assert summary["alerts_created"] == 0
    assert summary["alerts_resolved"] == 1

    active_alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.status == "active")
        .all()
    )
    assert active_alerts == []


def test_rerunning_evaluation_unchanged_is_idempotent(db_session, demo_deployment, admin_user):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)
    service = AlertEvaluationService(db_session)
    service.evaluate_all()
    summary_second_run = service.evaluate_all()

    assert summary_second_run["alerts_created"] == 0
    assert summary_second_run["alerts_resolved"] == 0

    active_alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.status == "active")
        .all()
    )
    assert len(active_alerts) == 1


def test_anomaly_detection_creates_alert(db_session, demo_deployment, admin_user):
    db_session.add(
        AnomalyDetection(
            deployment_id=demo_deployment.id,
            metric_type="resource_usage_composite",
            anomaly_score=0.42,
            is_anomaly=True,
            detected_at=datetime(2026, 7, 15, 12, 0, 0),
            details="{}",
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_type == "anomaly_detected"
    assert alert.severity == "warning"


def test_low_failure_probability_does_not_alert(db_session, demo_deployment, admin_user):
    db_session.add(
        FailurePrediction(
            deployment_id=demo_deployment.id,
            failure_type="deployment_failure",
            probability=0.3,
            predicted_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    summary = AlertEvaluationService(db_session).evaluate_all()

    assert summary["alerts_created"] == 0


def test_high_failure_probability_creates_critical_alert(db_session, demo_deployment, admin_user):
    db_session.add(
        FailurePrediction(
            deployment_id=demo_deployment.id,
            failure_type="deployment_failure",
            probability=0.85,
            predicted_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_type == "failure_risk"
    assert alert.severity == "critical"


def test_no_admin_users_skips_notification_without_error(db_session, demo_deployment):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)

    summary = AlertEvaluationService(db_session).evaluate_all()

    assert summary["alerts_created"] == 1
    assert summary["notifications_sent"] == 0
