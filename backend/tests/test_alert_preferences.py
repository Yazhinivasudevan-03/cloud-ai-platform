"""Unit tests for app.notifications.alert_preferences (Phase 23) - pure
logic, no DB needed."""
import json

from app.notifications.alert_preferences import (
    ALL_CATEGORIES,
    category_and_tier_for_alert_type,
    default_preferences,
    load_preferences,
    wants_notification,
)


def test_default_preferences_cover_every_category_fully_enabled():
    prefs = default_preferences()
    assert set(prefs.keys()) == set(ALL_CATEGORIES)
    for category, value in prefs.items():
        assert value["enabled"] is True


def test_category_and_tier_parses_tiered_alert_types():
    assert category_and_tier_for_alert_type("cpu_elevated") == ("cpu", "warning")
    assert category_and_tier_for_alert_type("cpu_high") == ("cpu", "critical")
    assert category_and_tier_for_alert_type("cpu_saturated") == ("cpu", "saturated")
    assert category_and_tier_for_alert_type("cost_elevated") == ("cloud_cost", "warning")
    assert category_and_tier_for_alert_type("storage_high") == ("storage", "critical")
    assert category_and_tier_for_alert_type("pod_restart_saturated") == ("pod_restart", "saturated")


def test_category_and_tier_parses_simple_alert_types():
    assert category_and_tier_for_alert_type("node_failure") == ("node_failure", None)
    assert category_and_tier_for_alert_type("container_failure") == ("container_failure", None)
    assert category_and_tier_for_alert_type("anomaly_detected") == ("ai_prediction", None)
    assert category_and_tier_for_alert_type("failure_risk") == ("ai_prediction", None)
    assert category_and_tier_for_alert_type("resource_optimization") == ("resource_optimization", None)


def test_category_and_tier_unknown_alert_type_returns_none():
    assert category_and_tier_for_alert_type("totally_unknown_type") == (None, None)


def test_load_preferences_defaults_when_null():
    assert load_preferences(None) == default_preferences()


def test_load_preferences_defaults_when_garbage_json():
    assert load_preferences("not json") == default_preferences()


def test_load_preferences_fills_in_missing_categories():
    partial = json.dumps({"cpu": {"enabled": True, "warning": False, "critical": True, "saturated": True}})
    prefs = load_preferences(partial)
    assert prefs["cpu"]["warning"] is False
    assert prefs["memory"]["enabled"] is True  # untouched category still defaults enabled


def test_wants_notification_true_by_default():
    assert wants_notification(default_preferences(), "cpu_elevated") is True
    assert wants_notification(default_preferences(), "node_failure") is True


def test_wants_notification_false_when_category_disabled():
    prefs = default_preferences()
    prefs["cpu"]["enabled"] = False
    assert wants_notification(prefs, "cpu_elevated") is False


def test_wants_notification_false_when_specific_tier_disabled():
    prefs = default_preferences()
    prefs["cpu"]["warning"] = False
    assert wants_notification(prefs, "cpu_elevated") is False
    assert wants_notification(prefs, "cpu_high") is True  # other tiers unaffected


def test_wants_notification_simple_category_ignores_tier_toggle():
    prefs = default_preferences()
    prefs["node_failure"]["enabled"] = False
    assert wants_notification(prefs, "node_failure") is False


def test_wants_notification_fails_open_for_unknown_alert_type():
    prefs = default_preferences()
    assert wants_notification(prefs, "some_future_alert_type") is True
