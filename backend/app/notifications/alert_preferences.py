"""Per-user alert-type/tier notification preferences (Phase 23).

Every alert type the engine can produce maps to one of 15 categories,
matching the platform's own alert taxonomy. 11 are "tiered" (warning/
critical/saturated - the 60/80/90% pattern already established by CPU/
Memory/Disk/Network/Cloud Cost in Phase 20/21); the remaining 4 are
pure state/event detections with no percentage to tier.

A user's stored `NotificationSetting.alert_preferences` is a JSON blob
of `{category: {"enabled": bool, "warning": bool, "critical": bool,
"saturated": bool}}`. Any category (or the whole column) left unset
defaults to fully enabled, so a user who predates this feature - or has
never touched their preferences - keeps today's always-on behavior
exactly as before.

This module only gates OUT-OF-BAND notification channels (email/SMS/
Telegram/Slack/Teams) - see app/notifications/dispatcher.py. The
in-app dashboard/Notification Bell feed is never suppressed by it,
matching the existing do-not-disturb precedent in that same module.
"""
import json

TIERED_CATEGORIES = (
    "cpu",
    "memory",
    "disk",
    "network",
    "storage",
    "cloud_usage",
    "cloud_cost",
    "api_latency",
    "error_rate",
    "pod_restart",
    "security",
)
SIMPLE_CATEGORIES = ("node_failure", "container_failure", "ai_prediction", "resource_optimization")
ALL_CATEGORIES = TIERED_CATEGORIES + SIMPLE_CATEGORIES

_TIER_SUFFIXES = {
    "_elevated": "warning",
    "_high": "critical",
    "_saturated": "saturated",
}

# alert_type prefixes that don't match their category name 1:1.
_CATEGORY_ALIASES = {"cost": "cloud_cost"}

_SIMPLE_ALERT_TYPES = {
    "node_failure": "node_failure",
    "container_failure": "container_failure",
    "anomaly_detected": "ai_prediction",
    "failure_risk": "ai_prediction",
    "resource_optimization": "resource_optimization",
}


def default_preferences() -> dict:
    """Every category and tier enabled - the implicit behavior for any
    user with no `alert_preferences` saved yet."""
    return {
        category: (
            {"enabled": True, "warning": True, "critical": True, "saturated": True}
            if category in TIERED_CATEGORIES
            else {"enabled": True}
        )
        for category in ALL_CATEGORIES
    }


def load_preferences(alert_preferences_json: str | None) -> dict:
    """Parses the stored JSON, filling in `default_preferences()` for any
    category (or sub-field) missing from it - additive so a partially-set
    blob (e.g. saved before a new category existed) never accidentally
    reads as "disabled"."""
    defaults = default_preferences()
    if not alert_preferences_json:
        return defaults
    try:
        stored = json.loads(alert_preferences_json)
    except (ValueError, TypeError):
        return defaults
    for category, default_value in defaults.items():
        stored_value = stored.get(category)
        if isinstance(stored_value, dict):
            defaults[category] = {**default_value, **stored_value}
    return defaults


def category_and_tier_for_alert_type(alert_type: str) -> tuple[str | None, str | None]:
    """Returns (category, tier) for a given Alert.alert_type string, or
    (None, None) if it doesn't match any known category - an unrecognized
    future alert type fails open (never gated) rather than silently
    dropped."""
    if alert_type in _SIMPLE_ALERT_TYPES:
        return _SIMPLE_ALERT_TYPES[alert_type], None

    for suffix, tier in _TIER_SUFFIXES.items():
        if alert_type.endswith(suffix):
            prefix = alert_type[: -len(suffix)]
            category = _CATEGORY_ALIASES.get(prefix, prefix)
            if category in TIERED_CATEGORIES:
                return category, tier

    return None, None


def wants_notification(preferences: dict, alert_type: str) -> bool:
    """Whether a user's preferences allow an out-of-band notification for
    this specific alert. Fails open (True) for anything unrecognized -
    gating must never silently swallow a genuinely new alert type just
    because this module doesn't know about it yet."""
    category, tier = category_and_tier_for_alert_type(alert_type)
    if category is None:
        return True

    category_prefs = preferences.get(category)
    if not isinstance(category_prefs, dict):
        return True

    if not category_prefs.get("enabled", True):
        return False
    if tier is None:
        return True
    return category_prefs.get(tier, True)
