"""Fan-out: given a newly created Alert, notify every admin user.

Dashboard notifications are always recorded (the `Notification` row itself
*is* the dashboard entry - no external delivery needed). Email is inherently
per-user (each admin has their own address), so it's attempted once per
admin. Slack/Telegram are shared-channel destinations, not per-user inboxes,
so each is attempted exactly once per alert - but a `Notification` row is
still recorded per admin per successful channel, so every admin's
notification history reflects that they would have seen it there.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.notification import Notification
from app.models.user import Role, User, user_roles
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
from app.notifications.telegram_notifier import send_telegram_message
from app.utils.logger import get_logger

logger = get_logger("notifications.dispatcher")


def _admin_users(db: Session) -> list[User]:
    stmt = (
        select(User)
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(Role, Role.id == user_roles.c.role_id)
        .where(Role.name == "admin", User.is_active.is_(True))
    )
    return list(db.scalars(stmt).unique().all())


def dispatch(db: Session, alert: Alert) -> int:
    """Notify every admin user across every enabled channel. Returns the
    number of Notification rows created."""
    admins = _admin_users(db)
    if not admins:
        logger.warning("No active admin users to notify for alert %s", alert.id)
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    subject = f"[{alert.severity.upper()}] {alert.alert_type}"

    # Shared-channel destinations: one delivery attempt total, not per admin.
    slack_delivered = send_slack_message(f"{subject}: {alert.message}")
    telegram_delivered = send_telegram_message(f"{subject}: {alert.message}")

    created = 0
    for user in admins:
        db.add(
            Notification(
                user_id=user.id,
                alert_id=alert.id,
                channel="dashboard",
                message=alert.message,
                is_read=False,
                sent_at=now,
            )
        )
        created += 1

        if send_email(user.email, subject, alert.message):
            db.add(
                Notification(
                    user_id=user.id,
                    alert_id=alert.id,
                    channel="email",
                    message=alert.message,
                    is_read=False,
                    sent_at=now,
                )
            )
            created += 1

        if slack_delivered:
            db.add(
                Notification(
                    user_id=user.id,
                    alert_id=alert.id,
                    channel="slack",
                    message=alert.message,
                    is_read=False,
                    sent_at=now,
                )
            )
            created += 1

        if telegram_delivered:
            db.add(
                Notification(
                    user_id=user.id,
                    alert_id=alert.id,
                    channel="telegram",
                    message=alert.message,
                    is_read=False,
                    sent_at=now,
                )
            )
            created += 1

    # Deliberately no commit here - the caller (AlertEvaluationService) owns
    # the transaction boundary so a whole deployment's evaluation commits
    # atomically alongside the Alert row this dispatch is attached to.
    return created
