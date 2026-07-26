"""Direct tests for app.notifications.dispatcher.dispatch() - the per-user
opt-in, do-not-disturb, and shared-destination dedup logic (Phase 20).
Exercised directly against a real Alert row rather than through the full
alert-evaluation pipeline, since that's already covered by
test_alert_evaluation.py.
"""
from datetime import datetime, time
from unittest.mock import MagicMock, patch

import pytest

from app.models.alert import Alert
from app.models.deployment import Deployment
from app.models.microservice import Microservice
from app.models.notification import Notification
from app.models.notification_setting import NotificationSetting
from app.models.project import Project
from app.models.user import Role, User
from app.notifications.dispatcher import dispatch


@pytest.fixture()
def demo_deployment(db_session):
    owner = User(
        username="dispatch_owner", email="dispatch_owner@example.com",
        hashed_password="not-a-real-hash", is_active=True, is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()
    project = Project(name="Dispatch Demo", owner_id=owner.id)
    db_session.add(project)
    db_session.flush()
    microservice = Microservice(project_id=project.id, name="dispatch-service")
    db_session.add(microservice)
    db_session.flush()
    deployment = Deployment(microservice_id=microservice.id, name="dispatch-deploy")
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)
    return deployment


def _make_admin(db_session, username: str) -> User:
    admin_role = db_session.query(Role).filter(Role.name == "admin").one()
    user = User(
        username=username, email=f"{username}@example.com",
        hashed_password="not-a-real-hash", is_active=True, is_superuser=False,
    )
    user.roles.append(admin_role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_alert(db_session, deployment_id: int) -> Alert:
    alert = Alert(
        deployment_id=deployment_id, alert_type="cpu_elevated", severity="warning",
        threshold_percent=60.0, message="CPU is elevated", status="active",
        triggered_at=datetime(2026, 7, 15, 12, 0, 0),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    return alert


def test_dashboard_notification_always_recorded_even_during_dnd(db_session, demo_deployment):
    admin = _make_admin(db_session, "dispatch_dnd_a")
    db_session.add(
        NotificationSetting(
            user_id=admin.id, dnd_start_time=time(0, 0), dnd_end_time=time(23, 59, 59)
        )
    )
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    created = dispatch(db_session, alert)
    db_session.commit()

    assert created == 1  # dashboard only - every out-of-band channel suppressed by DND
    channels = {
        n.channel for n in db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    }
    assert channels == {"dashboard"}


def test_instant_alerts_disabled_suppresses_everything_but_dashboard(db_session, demo_deployment):
    admin = _make_admin(db_session, "dispatch_instant_off")
    db_session.add(NotificationSetting(user_id=admin.id, instant_alerts_enabled=False))
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    created = dispatch(db_session, alert)
    db_session.commit()

    assert created == 1
    channels = {
        n.channel for n in db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    }
    assert channels == {"dashboard"}


def test_disabled_channel_is_never_attempted(db_session, demo_deployment):
    """slack_enabled defaults to False - dispatch must not even call the
    Slack notifier, let alone record a Notification for it."""
    _make_admin(db_session, "dispatch_no_slack")
    alert = _make_alert(db_session, demo_deployment.id)

    with patch("app.notifications.dispatcher.send_slack_message") as mock_slack:
        dispatch(db_session, alert)
    db_session.commit()

    mock_slack.assert_not_called()


def test_two_admins_sharing_the_global_slack_webhook_only_post_once(db_session, demo_deployment, monkeypatch):
    from app.config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://hooks.slack.example/shared")

    admin_a = _make_admin(db_session, "dispatch_shared_a")
    admin_b = _make_admin(db_session, "dispatch_shared_b")
    for admin in (admin_a, admin_b):
        db_session.add(NotificationSetting(user_id=admin.id, slack_enabled=True))
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        dispatch(db_session, alert)
    db_session.commit()

    mock_post.assert_called_once()  # one shared webhook, one post - not two
    slack_notifications = (
        db_session.query(Notification)
        .filter(Notification.alert_id == alert.id, Notification.channel == "slack")
        .all()
    )
    assert len(slack_notifications) == 2  # both admins still get their own history row


def test_two_admins_with_different_personal_slack_webhooks_each_get_posted_to(
    db_session, demo_deployment
):
    from app.utils.crypto import encrypt_credentials

    admin_a = _make_admin(db_session, "dispatch_personal_a")
    admin_b = _make_admin(db_session, "dispatch_personal_b")
    db_session.add(
        NotificationSetting(
            user_id=admin_a.id,
            slack_enabled=True,
            credentials_encrypted=encrypt_credentials(
                {"slack_webhook_url": "https://hooks.slack.example/personal-a"}
            ),
        )
    )
    db_session.add(
        NotificationSetting(
            user_id=admin_b.id,
            slack_enabled=True,
            credentials_encrypted=encrypt_credentials(
                {"slack_webhook_url": "https://hooks.slack.example/personal-b"}
            ),
        )
    )
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.slack_notifier.httpx.post", return_value=mock_response) as mock_post:
        dispatch(db_session, alert)
    db_session.commit()

    assert mock_post.call_count == 2  # two distinct personal webhooks, two posts
    posted_urls = {call.args[0] for call in mock_post.call_args_list}
    assert posted_urls == {
        "https://hooks.slack.example/personal-a",
        "https://hooks.slack.example/personal-b",
    }


# --- Multi-timezone notification enrichment (Phase 22) -----------------------


def test_email_body_unchanged_without_a_configured_deployment_timezone(db_session, demo_deployment):
    """Regression: deployments with no linked cloud account timezone must
    keep sending the exact same plain alert.message as before."""
    admin = _make_admin(db_session, "dispatch_tz_off")
    db_session.add(NotificationSetting(user_id=admin.id, email_enabled=True))
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email:
        dispatch(db_session, alert)
    db_session.commit()

    mock_email.assert_called_once_with(admin.email, "[WARNING] cpu_elevated", "CPU is elevated")


def test_email_and_slack_include_timezone_context_for_a_configured_deployment(
    db_session, demo_deployment, monkeypatch
):
    """Phase 22 worked example: a CPU alert for a deployment linked to an
    Asia/Kolkata (Mumbai) timezone entry includes Cloud Provider/Region/
    Deployment/Timezone/local+UTC alert time in the outgoing email/Slack
    text, without changing the core alert/message itself."""
    from app.config.settings import get_settings
    from app.models.cloud_account_timezone import CloudAccountTimezone
    from app.models.cloud_provider_account import CloudProviderAccount
    from app.utils.crypto import encrypt_credentials

    monkeypatch.setattr(get_settings(), "SLACK_WEBHOOK_URL", "https://hooks.slack.example/shared")

    account = CloudProviderAccount(
        user_id=demo_deployment.microservice.project.owner_id,
        provider="aws",
        account_name="mumbai-account",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "x", "secret_access_key": "y"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    timezone_entry = CloudAccountTimezone(
        cloud_provider_account_id=account.id, region="ap-south-1", label="Mumbai", timezone="Asia/Kolkata",
    )
    db_session.add(timezone_entry)
    db_session.commit()
    db_session.refresh(timezone_entry)

    demo_deployment.cloud_provider_account_id = account.id
    demo_deployment.cloud_account_timezone_id = timezone_entry.id
    db_session.commit()

    admin = _make_admin(db_session, "dispatch_tz_on")
    db_session.add(NotificationSetting(user_id=admin.id, email_enabled=True, slack_enabled=True))
    db_session.commit()

    alert = Alert(
        deployment_id=demo_deployment.id, alert_type="cpu_elevated", severity="warning",
        threshold_percent=60.0, message="CPU is elevated", status="active",
        triggered_at=datetime(2026, 8, 15, 17, 35, 0),
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email, patch(
        "app.notifications.slack_notifier.httpx.post", return_value=mock_response
    ) as mock_post:
        dispatch(db_session, alert)
    db_session.commit()

    email_body = mock_email.call_args.args[2]
    assert "CPU is elevated" in email_body
    assert "Cloud Provider: aws" in email_body
    assert "Region: ap-south-1" in email_body
    assert "Deployment: dispatch-deploy" in email_body
    assert "Timezone: Asia/Kolkata" in email_body
    assert "Alert Time (Local): 2026-08-15 23:05 IST" in email_body
    assert "Alert Time (UTC): 2026-08-15 17:35 UTC" in email_body

    slack_text = mock_post.call_args.kwargs["json"]["text"]
    assert "Asia/Kolkata" in slack_text
    assert "Alert Time (Local): 2026-08-15 23:05 IST" in slack_text


# --- Per-user alert-type/tier preference gating (Phase 23) ------------------


def test_disabled_category_suppresses_email_but_not_the_dashboard_entry(db_session, demo_deployment):
    import json

    admin = _make_admin(db_session, "dispatch_pref_a")
    setting = NotificationSetting(
        user_id=admin.id,
        email_enabled=True,
        alert_preferences=json.dumps({"cpu": {"enabled": False, "warning": True, "critical": True, "saturated": True}}),
    )
    db_session.add(setting)
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)  # alert_type="cpu_elevated"

    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email:
        created = dispatch(db_session, alert)
    db_session.commit()

    mock_email.assert_not_called()
    channels = {
        n.channel for n in db_session.query(Notification).filter(Notification.alert_id == alert.id).all()
    }
    assert channels == {"dashboard"}
    assert created == 1


def test_disabled_tier_suppresses_only_that_tier(db_session, demo_deployment):
    import json

    admin = _make_admin(db_session, "dispatch_pref_b")
    setting = NotificationSetting(
        user_id=admin.id,
        email_enabled=True,
        alert_preferences=json.dumps({"cpu": {"enabled": True, "warning": False, "critical": True, "saturated": True}}),
    )
    db_session.add(setting)
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)  # cpu_elevated = warning tier - disabled

    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email:
        dispatch(db_session, alert)
    db_session.commit()

    mock_email.assert_not_called()


def test_default_preferences_still_notify_when_unconfigured(db_session, demo_deployment):
    """A user who never touched alert_preferences (NULL column) keeps
    today's always-on behavior - the core backward-compatibility
    guarantee for this feature."""
    admin = _make_admin(db_session, "dispatch_pref_c")
    db_session.add(NotificationSetting(user_id=admin.id, email_enabled=True))
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email:
        dispatch(db_session, alert)
    db_session.commit()

    mock_email.assert_called_once()


def test_secondary_email_is_also_sent(db_session, demo_deployment):
    admin = _make_admin(db_session, "dispatch_pref_d")
    db_session.add(
        NotificationSetting(user_id=admin.id, email_enabled=True, secondary_email="backup@example.com")
    )
    db_session.commit()
    alert = _make_alert(db_session, demo_deployment.id)

    with patch("app.notifications.dispatcher.send_email", return_value=True) as mock_email:
        dispatch(db_session, alert)
    db_session.commit()

    assert mock_email.call_count == 2
    recipients = {call.args[0] for call in mock_email.call_args_list}
    assert recipients == {"dispatch_pref_d@example.com", "backup@example.com"}
