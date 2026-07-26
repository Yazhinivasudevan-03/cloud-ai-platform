"""Tests for the AlertEvaluationService rule engine, exercised directly
against the DB (not through the HTTP API) since it's triggered by the
scheduler/POST /alerts/evaluate, not by a request body.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.alert import Alert
from app.models.anomaly_detection import AnomalyDetection
from app.models.cloud_account_alert_threshold import CloudAccountAlertThreshold
from app.models.cloud_cost import CloudCost
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.deployment import Deployment
from app.models.failure_prediction import FailurePrediction
from app.models.microservice import Microservice
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.pod import Pod
from app.models.project import Project
from app.models.resource_usage import ResourceUsage
from app.models.user import Role, User
from app.services.alert_evaluation_service import AlertEvaluationService
from app.utils.crypto import encrypt_credentials


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


def _add_resource_usage(
    db_session, deployment_id: int, cpu_usage_percent: float, disk_usage_mb: float = 1000.0
):
    db_session.add(
        ResourceUsage(
            deployment_id=deployment_id,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_mb=500.0,
            disk_usage_mb=disk_usage_mb,
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
    isolation - an admin with a phone_number on file and sms_enabled in
    their NotificationSetting (Phase 20 - off by default) gets a real "sms"
    Notification row once Twilio is configured, mirroring how the
    pre-existing "dashboard" channel test above proves the base wiring."""
    from unittest.mock import MagicMock, patch

    from app.config.settings import get_settings
    from app.models.notification_setting import NotificationSetting

    settings = get_settings()
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACxxxx")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15005550006")
    admin_user.phone_number = "+14155552671"
    db_session.add(NotificationSetting(user_id=admin_user.id, sms_enabled=True))
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


# --- Memory alerting (Phase 20 - previously memory had no alert path at all) --


@pytest.fixture()
def demo_deployment_with_memory_limit(db_session, demo_deployment):
    demo_deployment.memory_limit_mb = 1000.0
    db_session.commit()
    db_session.refresh(demo_deployment)
    return demo_deployment


def _add_memory_usage(db_session, deployment_id: int, memory_usage_mb: float):
    db_session.add(
        ResourceUsage(
            deployment_id=deployment_id,
            cpu_usage_percent=10.0,  # comfortably below every CPU tier
            memory_usage_mb=memory_usage_mb,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()


def test_memory_alerting_is_skipped_without_a_configured_limit(db_session, demo_deployment):
    _add_memory_usage(db_session, demo_deployment.id, memory_usage_mb=950.0)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).count() == 0


@pytest.mark.parametrize(
    "memory_usage_mb,expected_alert_type,expected_severity",
    [
        (500.0, None, None),
        (650.0, "memory_elevated", "warning"),
        (850.0, "memory_high", "critical"),
        (950.0, "memory_saturated", "critical"),
    ],
)
def test_memory_threshold_tiers(
    db_session, demo_deployment_with_memory_limit, memory_usage_mb, expected_alert_type, expected_severity
):
    _add_memory_usage(db_session, demo_deployment_with_memory_limit.id, memory_usage_mb)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment_with_memory_limit.id, Alert.alert_type.like("memory_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity


# --- Per-cloud-account CPU/memory threshold overrides (Phase 20) --------------


@pytest.fixture()
def demo_cloud_account(db_session, demo_deployment_with_memory_limit):
    account = CloudProviderAccount(
        user_id=demo_deployment_with_memory_limit.microservice.project.owner_id,
        provider="aws",
        account_name="threshold-test-account",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "x", "secret_access_key": "y"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    demo_deployment_with_memory_limit.cloud_provider_account_id = account.id
    db_session.commit()
    return account


def test_custom_cpu_threshold_override_fires_where_the_global_default_would_not(
    db_session, demo_deployment_with_memory_limit, demo_cloud_account
):
    """Global ALERT_CPU_WARNING_THRESHOLD is 60 - 45% CPU would not alert
    under the default, but a custom, stricter override of 40 must."""
    db_session.add(
        CloudAccountAlertThreshold(cloud_provider_account_id=demo_cloud_account.id, cpu_warning_threshold=40.0)
    )
    db_session.commit()
    db_session.add(
        ResourceUsage(
            deployment_id=demo_deployment_with_memory_limit.id,
            cpu_usage_percent=45.0,
            memory_usage_mb=100.0,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment_with_memory_limit.id, Alert.alert_type == "cpu_elevated")
        .one()
    )
    assert alert.threshold_percent == 40.0


def test_threshold_override_only_applies_the_overridden_tier_others_stay_default(
    db_session, demo_deployment_with_memory_limit, demo_cloud_account
):
    """Only cpu_critical_threshold is overridden here - cpu_warning and
    cpu_saturated must still fall back to the platform-wide defaults."""
    db_session.add(
        CloudAccountAlertThreshold(cloud_provider_account_id=demo_cloud_account.id, cpu_critical_threshold=70.0)
    )
    db_session.commit()
    db_session.add(
        ResourceUsage(
            deployment_id=demo_deployment_with_memory_limit.id,
            cpu_usage_percent=75.0,  # above the custom critical (70) but below default saturated (100)
            memory_usage_mb=100.0,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment_with_memory_limit.id, Alert.alert_type == "cpu_high")
        .one()
    )
    assert alert.threshold_percent == 70.0
    assert alert.severity == "critical"


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


# --- Disk alerting (Phase 21) ----------------------------------------------


def test_disk_alerting_is_skipped_without_a_configured_limit(db_session, demo_deployment):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0, disk_usage_mb=950.0)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).count() == 0


@pytest.mark.parametrize(
    "disk_usage_mb,expected_alert_type,expected_severity",
    [
        (500.0, None, None),
        (650.0, "disk_elevated", "warning"),
        (850.0, "disk_high", "critical"),
        (950.0, "disk_saturated", "critical"),
    ],
)
def test_disk_threshold_tiers(
    db_session, demo_deployment, disk_usage_mb, expected_alert_type, expected_severity
):
    demo_deployment.disk_limit_mb = 1000.0
    db_session.commit()
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0, disk_usage_mb=disk_usage_mb)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("disk_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity


# --- Network alerting (Phase 21) --------------------------------------------


def test_network_alerting_is_skipped_without_a_configured_limit(db_session, demo_deployment):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).count() == 0


@pytest.mark.parametrize(
    "network_in_kbps,network_out_kbps,expected_alert_type,expected_severity",
    [
        (200.0, 100.0, None, None),  # 300/1000 = 30%
        (400.0, 250.0, "network_elevated", "warning"),  # 650/1000 = 65%
        (500.0, 350.0, "network_high", "critical"),  # 850/1000 = 85%
        (600.0, 350.0, "network_saturated", "critical"),  # 950/1000 = 95%
    ],
)
def test_network_threshold_tiers(
    db_session, demo_deployment, network_in_kbps, network_out_kbps, expected_alert_type, expected_severity
):
    demo_deployment.network_limit_kbps = 1000.0
    db_session.commit()
    db_session.add(
        ResourceUsage(
            deployment_id=demo_deployment.id,
            cpu_usage_percent=10.0,
            memory_usage_mb=100.0,
            disk_usage_mb=100.0,
            network_in_kbps=network_in_kbps,
            network_out_kbps=network_out_kbps,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("network_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity


# --- Multi-timezone alert enrichment (Phase 22) ------------------------------


def test_alert_has_null_timezone_fields_without_a_configured_deployment_timezone(
    db_session, demo_deployment
):
    """Regression: alerts for deployments with no linked cloud account
    timezone must keep behaving exactly as before - the new Phase 22
    fields exist but are null."""
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=65.0)

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    assert alert.alert_time_local is None
    assert alert.deployment_timezone is None
    assert alert.region is None
    assert alert.provider is None
    assert alert.alert_time_utc == alert.triggered_at


def test_alert_surfaces_local_time_for_a_deployment_with_a_configured_timezone(
    db_session, demo_deployment, admin_user
):
    """Phase 22 worked example: a CPU alert for a deployment linked to an
    Azure UK South (Europe/London) timezone entry surfaces the alert time
    in both UTC and BST, plus timezone/region/provider."""
    account = CloudProviderAccount(
        user_id=demo_deployment.microservice.project.owner_id,
        provider="azure",
        account_name="uk-south-account",
        region="uksouth",
        credentials_encrypted=encrypt_credentials({"access_key_id": "x", "secret_access_key": "y"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    from app.models.cloud_account_timezone import CloudAccountTimezone

    timezone_entry = CloudAccountTimezone(
        cloud_provider_account_id=account.id,
        region="uksouth",
        label="UK South",
        timezone="Europe/London",
    )
    db_session.add(timezone_entry)
    db_session.commit()
    db_session.refresh(timezone_entry)

    demo_deployment.cloud_provider_account_id = account.id
    demo_deployment.cloud_account_timezone_id = timezone_entry.id
    db_session.commit()

    db_session.add(
        ResourceUsage(
            deployment_id=demo_deployment.id,
            cpu_usage_percent=65.0,
            memory_usage_mb=500.0,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 8, 15, 17, 35, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).one()
    # triggered_at is "now" at evaluation time (not the resource usage's own
    # recorded_at), so assert self-consistency against the same conversion
    # utility rather than a hardcoded instant - format_local/compute_utc_offset
    # are exercised directly (and against a fixed DST-crossing date) in
    # test_timezones.py already.
    from app.utils.timezones import format_local

    assert alert.alert_time_utc == alert.triggered_at
    assert alert.alert_time_local == format_local(alert.triggered_at, "Europe/London")
    assert alert.deployment_timezone == "Europe/London"
    assert alert.region == "uksouth"
    assert alert.provider == "azure"


# --- Storage alerting (Phase 23 - reuses disk_usage_mb/disk_limit_mb) ------


def test_storage_alerting_is_skipped_without_a_configured_limit(db_session, demo_deployment):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0, disk_usage_mb=950.0)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.deployment_id == demo_deployment.id).count() == 0


@pytest.mark.parametrize(
    "disk_usage_mb,expected_alert_type,expected_severity",
    [
        (500.0, None, None),
        (650.0, "storage_elevated", "warning"),
        (850.0, "storage_high", "critical"),
        (950.0, "storage_saturated", "critical"),
    ],
)
def test_storage_threshold_tiers(
    db_session, demo_deployment, disk_usage_mb, expected_alert_type, expected_severity
):
    """Storage deliberately fires alongside Disk from the same underlying
    disk_usage_mb/disk_limit_mb data (see AlertEvaluationService's
    docstring) - a real signal under its own alert_type, not a duplicate
    data source."""
    demo_deployment.disk_limit_mb = 1000.0
    db_session.commit()
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0, disk_usage_mb=disk_usage_mb)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("storage_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity


# --- Cloud Usage alerting (Phase 23 - aggregate across cpu/memory/disk/network) --


def test_cloud_usage_alerting_is_skipped_with_only_cpu_configured(db_session, demo_deployment):
    """With no memory/disk/network limit configured, Cloud Usage would be a
    pure duplicate of the CPU alert - deliberately skipped rather than
    firing a meaningless second copy."""
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=95.0)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("cloud_usage_%"))
        .all()
    )
    assert alerts == []


def test_cloud_usage_takes_the_highest_of_the_configured_dimensions(db_session, demo_deployment):
    demo_deployment.memory_limit_mb = 1000.0
    demo_deployment.disk_limit_mb = 1000.0
    db_session.commit()
    db_session.add(
        ResourceUsage(
            deployment_id=demo_deployment.id,
            cpu_usage_percent=10.0,  # low
            memory_usage_mb=200.0,  # 20% - low
            disk_usage_mb=920.0,  # 92% - the highest dimension
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, 12, 0, 0),
        )
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("cloud_usage_%"))
        .one()
    )
    assert alert.alert_type == "cloud_usage_saturated"  # 92% >= the 90% saturated default
    assert alert.severity == "critical"


# --- Pod Restart alerting (Phase 23 - reuses Pod.restart_count) ------------


def test_pod_restart_alerting_is_skipped_with_no_pods_recorded(db_session, demo_deployment):
    _add_resource_usage(db_session, demo_deployment.id, cpu_usage_percent=10.0)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("pod_restart_%"))
        .all()
    )
    assert alerts == []


@pytest.mark.parametrize(
    "restart_count,expected_alert_type,expected_severity",
    [
        (2, None, None),
        (3, "pod_restart_elevated", "warning"),
        (5, "pod_restart_high", "critical"),
        (10, "pod_restart_saturated", "critical"),
    ],
)
def test_pod_restart_threshold_tiers(
    db_session, demo_deployment, restart_count, expected_alert_type, expected_severity
):
    db_session.add(
        Pod(deployment_id=demo_deployment.id, pod_name="pod-a", status="running", restart_count=restart_count)
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("pod_restart_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity


def test_pod_restart_uses_the_highest_restart_count_across_pods(db_session, demo_deployment):
    db_session.add_all(
        [
            Pod(deployment_id=demo_deployment.id, pod_name="pod-a", status="running", restart_count=1),
            Pod(deployment_id=demo_deployment.id, pod_name="pod-b", status="running", restart_count=7),
        ]
    )
    db_session.commit()

    AlertEvaluationService(db_session).evaluate_all()

    alert = (
        db_session.query(Alert)
        .filter(Alert.deployment_id == demo_deployment.id, Alert.alert_type.like("pod_restart_%"))
        .one()
    )
    assert alert.alert_type == "pod_restart_high"  # 7 restarts -> critical tier (>=5, <10)


# --- Cost alerting (Phase 21 - project-scoped, not deployment-scoped) -------


@pytest.fixture()
def demo_project(db_session):
    owner = User(
        username="cost_alert_owner", email="cost_alert_owner@example.com",
        hashed_password="not-a-real-hash", is_active=True, is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()
    project = Project(name="Cost Alerting Demo", owner_id=owner.id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _add_cloud_cost(db_session, project_id: int, cost_amount: float):
    today = date.today()
    month_start = today.replace(day=1)
    next_month_start = (month_start.replace(day=28) + timedelta(days=7)).replace(day=1)
    db_session.add(
        CloudCost(
            project_id=project_id,
            provider="aws",
            service_name="EC2",
            cost_amount=cost_amount,
            currency="USD",
            billing_period_start=month_start,
            billing_period_end=next_month_start - timedelta(days=1),
        )
    )
    db_session.commit()


def test_cost_alerting_is_skipped_without_a_configured_budget(db_session, demo_project):
    _add_cloud_cost(db_session, demo_project.id, 5000.0)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.project_id == demo_project.id).count() == 0


@pytest.mark.parametrize(
    "spend,expected_alert_type,expected_severity",
    [
        (500.0, None, None),
        (650.0, "cost_elevated", "warning"),
        (850.0, "cost_high", "critical"),
        (950.0, "cost_saturated", "critical"),
    ],
)
def test_cost_threshold_tiers(db_session, demo_project, spend, expected_alert_type, expected_severity):
    demo_project.monthly_budget = 1000.0
    db_session.commit()
    _add_cloud_cost(db_session, demo_project.id, spend)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.project_id == demo_project.id, Alert.alert_type.like("cost_%"))
        .all()
    )
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity
        assert alerts[0].deployment_id is None
        assert alerts[0].project_id == demo_project.id


def test_cost_alert_sums_multiple_services_in_the_same_month(db_session, demo_project):
    demo_project.monthly_budget = 1000.0
    db_session.commit()
    _add_cloud_cost(db_session, demo_project.id, 400.0)
    _add_cloud_cost(db_session, demo_project.id, 300.0)  # combined 700 = 70% -> elevated

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.project_id == demo_project.id).one()
    assert alert.alert_type == "cost_elevated"


def test_cost_alert_resolves_once_spend_drops_back_under_budget_next_evaluation(db_session, demo_project):
    """Simulates a corrected/reduced cost entry - the same idempotent
    resolve-on-clear lifecycle every other alert type already has."""
    demo_project.monthly_budget = 1000.0
    db_session.commit()
    cost = CloudCost(
        project_id=demo_project.id, provider="aws", service_name="EC2", cost_amount=950.0,
        currency="USD", billing_period_start=date.today().replace(day=1),
        billing_period_end=date.today().replace(day=1),
    )
    db_session.add(cost)
    db_session.commit()

    service = AlertEvaluationService(db_session)
    summary = service.evaluate_all()
    assert summary["alerts_created"] == 1

    cost.cost_amount = 100.0
    db_session.commit()
    summary = service.evaluate_all()

    assert summary["alerts_resolved"] == 1
    active = (
        db_session.query(Alert)
        .filter(Alert.project_id == demo_project.id, Alert.status == "active")
        .all()
    )
    assert active == []


def test_custom_project_cost_threshold_override(db_session, demo_project):
    demo_project.monthly_budget = 1000.0
    demo_project.cost_warning_threshold = 40.0
    db_session.commit()
    _add_cloud_cost(db_session, demo_project.id, 450.0)  # 45% - below default 60%, above custom 40%

    AlertEvaluationService(db_session).evaluate_all()

    alert = db_session.query(Alert).filter(Alert.project_id == demo_project.id).one()
    assert alert.alert_type == "cost_elevated"
    assert alert.threshold_percent == 40.0


# --- Security alerting (Phase 23 - reuses existing AuditLog rows) -----------


@pytest.fixture()
def demo_user(db_session):
    user = User(
        username="security_demo_user",
        email="security_demo_user@example.com",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _add_failed_login(db_session, user_id: int, when: datetime):
    db_session.add(
        AuditLog(
            user_id=user_id,
            action="POST /api/v1/auth/login",
            entity_type="auth",
            details="status=401",
            created_at=when,
        )
    )
    db_session.commit()


def test_security_alerting_is_skipped_below_the_warning_threshold(db_session, demo_user):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _ in range(2):  # below the default warning threshold of 3
        _add_failed_login(db_session, demo_user.id, now)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.user_id == demo_user.id).count() == 0


@pytest.mark.parametrize(
    "failed_attempts,expected_alert_type,expected_severity",
    [
        (2, None, None),
        (3, "security_elevated", "warning"),
        (5, "security_high", "critical"),
        (10, "security_saturated", "critical"),
    ],
)
def test_security_threshold_tiers(
    db_session, demo_user, failed_attempts, expected_alert_type, expected_severity
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _ in range(failed_attempts):
        _add_failed_login(db_session, demo_user.id, now)

    AlertEvaluationService(db_session).evaluate_all()

    alerts = db_session.query(Alert).filter(Alert.user_id == demo_user.id).all()
    if expected_alert_type is None:
        assert alerts == []
    else:
        assert len(alerts) == 1
        assert alerts[0].alert_type == expected_alert_type
        assert alerts[0].severity == expected_severity
        assert alerts[0].deployment_id is None
        assert alerts[0].project_id is None


def test_security_alert_ignores_failed_logins_outside_the_rolling_window(db_session, demo_user):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old = now - timedelta(minutes=30)  # outside the default 15-minute window
    for _ in range(10):
        _add_failed_login(db_session, demo_user.id, old)

    AlertEvaluationService(db_session).evaluate_all()

    assert db_session.query(Alert).filter(Alert.user_id == demo_user.id).count() == 0


def test_security_alert_resolves_once_failed_logins_age_out_of_the_window(db_session, demo_user):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _ in range(5):
        _add_failed_login(db_session, demo_user.id, now)
    service = AlertEvaluationService(db_session)
    summary = service.evaluate_all()
    assert summary["alerts_created"] == 1

    # Simulate time passing: age every recorded failed login out of the window.
    db_session.query(AuditLog).filter(AuditLog.user_id == demo_user.id).update(
        {"created_at": now - timedelta(minutes=30)}
    )
    db_session.commit()
    summary = service.evaluate_all()

    assert summary["alerts_resolved"] == 1
    active = (
        db_session.query(Alert)
        .filter(Alert.user_id == demo_user.id, Alert.status == "active")
        .all()
    )
    assert active == []


# --- API Latency / Error Rate alerting (Phase 23 - queries real Prometheus) --


def _platform_wide_alerts(db_session):
    return (
        db_session.query(Alert)
        .filter(Alert.deployment_id.is_(None), Alert.project_id.is_(None), Alert.user_id.is_(None))
        .all()
    )


def test_platform_metrics_skipped_when_prometheus_has_no_data(db_session, monkeypatch):
    import app.services.alert_evaluation_service as svc

    monkeypatch.setattr(svc, "average_latency_ms", lambda: None)
    monkeypatch.setattr(svc, "error_rate_percent", lambda: None)

    AlertEvaluationService(db_session).evaluate_all()

    assert _platform_wide_alerts(db_session) == []


def test_api_latency_alert_fires_from_a_real_prometheus_reading(db_session, monkeypatch):
    import app.services.alert_evaluation_service as svc

    monkeypatch.setattr(svc, "average_latency_ms", lambda: 1500.0)  # above the 1000ms critical default
    monkeypatch.setattr(svc, "error_rate_percent", lambda: None)

    AlertEvaluationService(db_session).evaluate_all()

    alert = next(a for a in _platform_wide_alerts(db_session) if a.alert_type.startswith("api_latency_"))
    assert alert.alert_type == "api_latency_high"
    assert alert.severity == "critical"


def test_error_rate_alert_fires_from_a_real_prometheus_reading(db_session, monkeypatch):
    import app.services.alert_evaluation_service as svc

    monkeypatch.setattr(svc, "average_latency_ms", lambda: None)
    monkeypatch.setattr(svc, "error_rate_percent", lambda: 12.0)  # above the 10% saturated default

    AlertEvaluationService(db_session).evaluate_all()

    alert = next(a for a in _platform_wide_alerts(db_session) if a.alert_type.startswith("error_rate_"))
    assert alert.alert_type == "error_rate_saturated"
    assert alert.severity == "critical"


def test_platform_metric_alert_resolves_once_back_under_threshold(db_session, monkeypatch):
    import app.services.alert_evaluation_service as svc

    monkeypatch.setattr(svc, "average_latency_ms", lambda: 1500.0)
    monkeypatch.setattr(svc, "error_rate_percent", lambda: None)
    service = AlertEvaluationService(db_session)
    summary = service.evaluate_all()
    assert summary["alerts_created"] == 1

    monkeypatch.setattr(svc, "average_latency_ms", lambda: 100.0)  # comfortably below every tier
    summary = service.evaluate_all()

    assert summary["alerts_resolved"] == 1
    assert [a for a in _platform_wide_alerts(db_session) if a.status == "active"] == []
