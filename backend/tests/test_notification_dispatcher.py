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
