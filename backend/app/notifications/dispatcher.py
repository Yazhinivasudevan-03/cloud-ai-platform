"""Fan-out: given a newly created Alert, notify the alert's actual owner(s)
according to their own NotificationSetting (Phase 20) - channel opt-in,
do-not-disturb window, and per-user Telegram/Slack/Teams credential
overrides.

Phase 24: this used to notify every admin-role user platform-wide,
matching the old shared-organization model where any admin could act on
any alert. Now that data is fully tenant-isolated, an alert is only ever
relevant to the tenant it actually belongs to - see `_recipients()` below
for how each of Alert's scopes (deployment/project/user/platform-wide)
resolves to its real owner(s). A platform is_superuser is not
additionally notified for other tenants' scoped alerts (they can still
see everything via the global listing endpoints, just aren't paged for
it) - mirrors how a real SaaS platform operator isn't paged per-customer.

Dashboard notifications are always recorded regardless of any preference
below (the `Notification` row itself *is* the dashboard entry - a user's
in-app inbox should never silently lose an alert just because they were in
a do-not-disturb window; DND only suppresses the out-of-band pings).

Email and SMS are inherently per-user (each recipient has their own
address/phone_number). Telegram/Slack/Teams *can* be per-user (a personal
bot chat ID or webhook) or fall back to a platform-wide shared destination
(Telegram bot token, Slack webhook) - when multiple recipients resolve to
the exact same destination (e.g. everyone sharing the one global Slack
webhook, which is the default when nobody has configured their own), that
destination is only ever posted to once per alert, not once per recipient,
so a shared channel doesn't get spammed with duplicate copies of the same
message. In practice this now rarely applies (deployment/project/user-
scoped alerts resolve to a single recipient), but still matters for the
platform-wide case, where every is_superuser is notified.
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.notification import Notification
from app.models.notification_setting import NotificationSetting
from app.models.user import User
from app.notifications.alert_preferences import load_preferences, wants_notification
from app.notifications.email_notifier import send_email
from app.notifications.slack_notifier import send_slack_message
from app.notifications.sms_notifier import send_sms
from app.notifications.teams_notifier import send_teams_message
from app.notifications.telegram_notifier import send_telegram_message
from app.repositories.notification_setting_repository import NotificationSettingRepository
from app.services.notification_setting_service import NotificationSettingService
from app.utils.logger import get_logger

logger = get_logger("notifications.dispatcher")


def _enrich_message(alert: Alert) -> str:
    """Appends Cloud Provider/Region/Deployment/Timezone/local+UTC alert
    time context (Phase 22) to the out-of-band notification text, only
    when the alert's deployment is linked to a configured cloud account
    timezone entry. Byte-identical to alert.message otherwise, so every
    existing notification for a deployment without one configured (the
    vast majority, pre-Phase-22) is completely unaffected."""
    if not alert.deployment_timezone:
        return alert.message
    lines = [alert.message, ""]
    if alert.provider:
        lines.append(f"Cloud Provider: {alert.provider}")
    if alert.region:
        lines.append(f"Region: {alert.region}")
    if alert.deployment is not None:
        lines.append(f"Deployment: {alert.deployment.name}")
    lines.append(f"Timezone: {alert.deployment_timezone}")
    lines.append(f"Alert Time (Local): {alert.alert_time_local}")
    lines.append(f"Alert Time (UTC): {alert.alert_time_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    return "\n".join(lines)


def _superusers(db: Session) -> list[User]:
    stmt = select(User).where(User.is_superuser.is_(True), User.is_active.is_(True))
    return list(db.scalars(stmt).unique().all())


def _recipients(db: Session, alert: Alert) -> list[User]:
    """Resolves an alert's real owner(s) (Phase 24) - each of Alert's
    mutually-exclusive scopes maps to a single tenant (or, for a genuinely
    platform-wide alert, every platform is_superuser):
    - deployment-scoped -> the deployment's project owner
    - project-scoped (cost alerts) -> that project's owner
    - user-scoped (security alerts) -> that same user
    - platform-wide (all three null - API Latency/Error Rate/Node Failure/
      Container Failure) -> every is_superuser
    An inactive resolved owner is excluded (mirrors _superusers' own
    is_active filter for the platform-wide case)."""
    if alert.deployment_id is not None:
        owner = alert.deployment.microservice.project.owner
        return [owner] if owner.is_active else []
    if alert.project_id is not None:
        owner = alert.project.owner
        return [owner] if owner.is_active else []
    if alert.user_id is not None:
        user = alert.user
        return [user] if user is not None and user.is_active else []
    return _superusers(db)


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
    """Notify the alert's real owner(s) (Phase 24 - see _recipients())
    across every channel they've enabled, unless they're in their own
    do-not-disturb window. Returns the number of Notification rows
    created."""
    recipients = _recipients(db, alert)
    if not recipients:
        logger.warning("No active recipient to notify for alert %s", alert.id)
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    subject = f"[{alert.severity.upper()}] {alert.alert_type}"
    enriched_message = _enrich_message(alert)
    text = f"{subject}: {enriched_message}"

    setting_repository = NotificationSettingRepository(db)
    slack_delivered_by_webhook: dict[str, bool] = {}
    telegram_delivered_by_destination: dict[tuple[str, str], bool] = {}
    teams_delivered_by_webhook: dict[str, bool] = {}

    created = 0
    for user in recipients:
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

        # Per-user alert-type/tier preferences (Phase 23) gate only these
        # out-of-band channels - the dashboard entry above is never
        # suppressed by them, matching the do-not-disturb precedent above.
        if not wants_notification(load_preferences(setting.alert_preferences), alert.alert_type):
            continue

        creds = None  # decrypted lazily - most users have no per-user overrides at all

        if setting.email_enabled and send_email(user.email, subject, enriched_message):
            db.add(
                Notification(
                    user_id=user.id, alert_id=alert.id, channel="email",
                    message=alert.message, is_read=False, sent_at=now,
                )
            )
            created += 1
            if setting.secondary_email:
                # Best-effort - a secondary address is a convenience CC, not
                # tracked as its own Notification row/channel.
                send_email(setting.secondary_email, subject, enriched_message)

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
