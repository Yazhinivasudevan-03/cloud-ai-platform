"""Fan-out: given a newly created Alert, notify every admin user according
to their own NotificationSetting (Phase 20) - channel opt-in, do-not-disturb
window, and per-user Telegram/Slack/Teams credential overrides.

Dashboard notifications are always recorded regardless of any preference
below (the `Notification` row itself *is* the dashboard entry - a user's
in-app inbox should never silently lose an alert just because they were in
a do-not-disturb window; DND only suppresses the out-of-band pings).

Email and SMS are inherently per-user (each admin has their own
address/phone_number). Telegram/Slack/Teams *can* be per-user (a personal
bot chat ID or webhook) or fall back to a platform-wide shared destination
(Telegram bot token, Slack webhook) - when multiple admins resolve to the
exact same destination (e.g. everyone sharing the one global Slack
webhook, which is the default when nobody has configured their own), that
destination is only ever posted to once per alert, not once per admin, so
a shared channel doesn't get spammed with duplicate copies of the same
message.
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.notification import Notification
from app.models.notification_setting import NotificationSetting
from app.models.user import Role, User, user_roles
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
from app.notifications.sms_notifier import send_sms
from app.notifications.teams_notifier import send_teams_message
from app.notifications.telegram_notifier import send_telegram_message
from app.repositories.notification_setting_repository import NotificationSettingRepository
from app.services.notification_setting_service import NotificationSettingService
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


def _in_dnd_window(setting: NotificationSetting, now_utc: datetime) -> bool:
    if setting.dnd_start_time is None or setting.dnd_end_time is None:
        return False
    try:
        tz = ZoneInfo(setting.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    local_time = now_utc.replace(tzinfo=timezone.utc).astimezone(tz).time()

    start, end = setting.dnd_start_time, setting.dnd_end_time
    if start <= end:
        return start <= local_time < end
    return local_time >= start or local_time < end  # window wraps midnight, e.g. 22:00-07:00


def dispatch(db: Session, alert: Alert) -> int:
    """Notify every admin user across every channel they've enabled, unless
    they're in their own do-not-disturb window. Returns the number of
    Notification rows created."""
    admins = _admin_users(db)
    if not admins:
        logger.warning("No active admin users to notify for alert %s", alert.id)
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    subject = f"[{alert.severity.upper()}] {alert.alert_type}"
    text = f"{subject}: {alert.message}"

    setting_repository = NotificationSettingRepository(db)
    slack_delivered_by_webhook: dict[str, bool] = {}
    telegram_delivered_by_destination: dict[tuple[str, str], bool] = {}
    teams_delivered_by_webhook: dict[str, bool] = {}

    created = 0
    for user in admins:
        setting = setting_repository.get_or_create(user.id)
        db.add(
            Notification(
                user_id=user.id, alert_id=alert.id, channel="dashboard",
                message=alert.message, is_read=False, sent_at=now,
            )
        )
        created += 1

        if not setting.instant_alerts_enabled or _in_dnd_window(setting, now):
            continue

        creds = None  # decrypted lazily - most users have no per-user overrides at all

        if setting.email_enabled and send_email(user.email, subject, alert.message):
            db.add(
                Notification(
                    user_id=user.id, alert_id=alert.id, channel="email",
                    message=alert.message, is_read=False, sent_at=now,
                )
            )
            created += 1

        if setting.sms_enabled and send_sms(user.phone_number, text):
            db.add(
                Notification(
                    user_id=user.id, alert_id=alert.id, channel="sms",
                    message=alert.message, is_read=False, sent_at=now,
                )
            )
            created += 1

        if setting.telegram_enabled:
            creds = creds if creds is not None else NotificationSettingService(db).decrypt(setting)
            bot_token = creds.get("telegram_bot_token") or ""
            chat_id = creds.get("telegram_chat_id") or ""
            destination = (bot_token, chat_id)
            if destination not in telegram_delivered_by_destination:
                telegram_delivered_by_destination[destination] = send_telegram_message(
                    text, bot_token=creds.get("telegram_bot_token"), chat_id=creds.get("telegram_chat_id")
                )
            if telegram_delivered_by_destination[destination]:
                db.add(
                    Notification(
                        user_id=user.id, alert_id=alert.id, channel="telegram",
                        message=alert.message, is_read=False, sent_at=now,
                    )
                )
                created += 1

        if setting.slack_enabled:
            creds = creds if creds is not None else NotificationSettingService(db).decrypt(setting)
            webhook_url = creds.get("slack_webhook_url") or ""
            if webhook_url not in slack_delivered_by_webhook:
                slack_delivered_by_webhook[webhook_url] = send_slack_message(
                    text, webhook_url=creds.get("slack_webhook_url")
                )
            if slack_delivered_by_webhook[webhook_url]:
                db.add(
                    Notification(
                        user_id=user.id, alert_id=alert.id, channel="slack",
                        message=alert.message, is_read=False, sent_at=now,
                    )
                )
                created += 1

        if setting.teams_enabled:
            creds = creds if creds is not None else NotificationSettingService(db).decrypt(setting)
            webhook_url = creds.get("teams_webhook_url") or ""
            if webhook_url and webhook_url not in teams_delivered_by_webhook:
                teams_delivered_by_webhook[webhook_url] = send_teams_message(text, webhook_url)
            if teams_delivered_by_webhook.get(webhook_url):
                db.add(
                    Notification(
                        user_id=user.id, alert_id=alert.id, channel="teams",
                        message=alert.message, is_read=False, sent_at=now,
                    )
                )
                created += 1

    # Deliberately no commit here - the caller (AlertEvaluationService) owns
    # the transaction boundary so a whole deployment's evaluation commits
    # atomically alongside the Alert row this dispatch is attached to.
    return created
