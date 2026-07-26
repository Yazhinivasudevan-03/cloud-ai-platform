"""Unit tests for app.integrations.kubernetes_monitor (Phase 23) - mocks
the kubernetes client so these run without a real cluster reachable, and
verify the disabled-by-default / unreachable-cluster paths return None
(never an empty list, which would misleadingly read as "checked, healthy")."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config.settings import get_settings
from app.integrations import kubernetes_monitor


def test_disabled_by_default_returns_none_for_nodes(monkeypatch):
    monkeypatch.setattr(get_settings(), "ALERT_KUBERNETES_MONITORING_ENABLED", False)
    assert kubernetes_monitor.is_enabled() is False
    assert kubernetes_monitor.list_unhealthy_nodes() is None


def test_disabled_by_default_returns_none_for_containers(monkeypatch):
    monkeypatch.setattr(get_settings(), "ALERT_KUBERNETES_MONITORING_ENABLED", False)
    assert kubernetes_monitor.list_unhealthy_containers() is None


def _node(name: str, ready: bool, reason: str | None = None):
    condition = SimpleNamespace(type="Ready", status="True" if ready else "False", reason=reason)
    return SimpleNamespace(metadata=SimpleNamespace(name=name), status=SimpleNamespace(conditions=[condition]))


def test_list_unhealthy_nodes_returns_none_when_cluster_unreachable(monkeypatch):
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    with patch.object(kubernetes_monitor, "_core_v1_api", side_effect=Exception("connection refused")):
        assert kubernetes_monitor.list_unhealthy_nodes() is None


def test_list_unhealthy_nodes_filters_to_not_ready(monkeypatch):
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    mock_api = MagicMock()
    mock_api.list_node.return_value = SimpleNamespace(
        items=[
            _node("node-a", ready=True),
            _node("node-b", ready=False, reason="NotReady"),
        ]
    )
    with patch.object(kubernetes_monitor, "_core_v1_api", return_value=mock_api):
        result = kubernetes_monitor.list_unhealthy_nodes()

    assert result is not None
    assert len(result) == 1
    assert result[0].name == "node-b"
    assert result[0].reason == "NotReady"


def test_list_unhealthy_nodes_empty_list_when_all_healthy(monkeypatch):
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    mock_api = MagicMock()
    mock_api.list_node.return_value = SimpleNamespace(items=[_node("node-a", ready=True)])
    with patch.object(kubernetes_monitor, "_core_v1_api", return_value=mock_api):
        result = kubernetes_monitor.list_unhealthy_nodes()

    assert result == []  # checked, genuinely healthy - a real empty list, not None


def _pod_with_container(
    pod_name: str,
    container_name: str,
    waiting_reason: str | None,
    restart_count: int = 0,
    init_container_name: str | None = None,
    init_waiting_reason: str | None = None,
):
    state = SimpleNamespace(
        waiting=SimpleNamespace(reason=waiting_reason) if waiting_reason else None,
        terminated=None,
    )
    container_status = SimpleNamespace(name=container_name, state=state, restart_count=restart_count)
    init_statuses = []
    if init_container_name:
        init_state = SimpleNamespace(
            waiting=SimpleNamespace(reason=init_waiting_reason) if init_waiting_reason else None,
            terminated=None,
        )
        init_statuses.append(SimpleNamespace(name=init_container_name, state=init_state, restart_count=0))
    return SimpleNamespace(
        metadata=SimpleNamespace(name=pod_name),
        status=SimpleNamespace(container_statuses=[container_status], init_container_statuses=init_statuses),
    )


def test_list_unhealthy_containers_filters_to_known_failure_reasons(monkeypatch):
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    mock_api = MagicMock()
    mock_api.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            _pod_with_container("backend-1", "backend", waiting_reason="CrashLoopBackOff", restart_count=12),
            _pod_with_container("frontend-1", "frontend", waiting_reason=None),
        ]
    )
    with patch.object(kubernetes_monitor, "_core_v1_api", return_value=mock_api):
        result = kubernetes_monitor.list_unhealthy_containers()

    assert result is not None
    assert len(result) == 1
    assert result[0].pod_name == "backend-1"
    assert result[0].reason == "CrashLoopBackOff"
    assert result[0].restart_count == 12


def test_list_unhealthy_containers_checks_init_containers_too(monkeypatch):
    """A pod stuck in Init:CrashLoopBackOff (a real case observed against
    this platform's own Helm-deployed backend - see docs/PHASE_23.md) is
    crash-looping in an init container, not the main one."""
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    mock_api = MagicMock()
    mock_api.list_namespaced_pod.return_value = SimpleNamespace(
        items=[
            _pod_with_container(
                "backend-1", "backend", waiting_reason=None,
                init_container_name="migrate", init_waiting_reason="CrashLoopBackOff",
            ),
        ]
    )
    with patch.object(kubernetes_monitor, "_core_v1_api", return_value=mock_api):
        result = kubernetes_monitor.list_unhealthy_containers()

    assert result is not None
    assert len(result) == 1
    assert result[0].pod_name == "backend-1"
    assert result[0].container_name == "migrate"
    assert result[0].reason == "CrashLoopBackOff"


def test_list_unhealthy_containers_returns_none_when_unreachable(monkeypatch):
    monkeypatch.setattr(kubernetes_monitor, "is_enabled", lambda: True)
    with patch.object(kubernetes_monitor, "_core_v1_api", side_effect=Exception("connection refused")):
        assert kubernetes_monitor.list_unhealthy_containers() is None
