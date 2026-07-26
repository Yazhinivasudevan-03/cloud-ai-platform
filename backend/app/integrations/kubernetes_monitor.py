"""Real Kubernetes cluster monitoring (Phase 23) - Node Failure / Container
Failure evaluators.

This is this platform's first live connection to a Kubernetes API server.
Phase 8 only verified that this platform's own Helm chart deploys
correctly on a real cluster, once, as a one-time check - nothing before
this phase ever queried a cluster's live state on an ongoing basis (see
docs/PHASE_8.md's disclosure to that effect).

Uses the official `kubernetes` client, which transparently loads
whichever kubeconfig / in-cluster service-account credentials are
available - this module implements no auth handling of its own.

Gated by ALERT_KUBERNETES_MONITORING_ENABLED (default off): most
environments running this platform (a plain `docker compose up`) have no
Kubernetes cluster at all to query, and a missing/unreachable cluster
must never be silently treated as "no failures" by an evaluator that
never actually ran - every function here returns `None` (never an empty
list) in that case, and callers must treat `None` as "skip", not "healthy".
"""
from dataclasses import dataclass

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("integrations.kubernetes")

_UNHEALTHY_NODE_REASONS = {"NotReady", "Unreachable", "Unknown"}
_UNHEALTHY_CONTAINER_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "OOMKilled",
    "Error",
}


@dataclass(frozen=True)
class NodeStatus:
    name: str
    reason: str


@dataclass(frozen=True)
class ContainerStatus:
    pod_name: str
    container_name: str
    reason: str
    restart_count: int


def is_enabled() -> bool:
    return get_settings().ALERT_KUBERNETES_MONITORING_ENABLED


def _core_v1_api():
    from kubernetes import client, config

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api()


def list_unhealthy_nodes() -> list[NodeStatus] | None:
    """`None` when monitoring is disabled or the cluster is unreachable -
    never an empty list in that case, which would misleadingly read as
    "checked, all healthy"."""
    if not is_enabled():
        return None
    try:
        api = _core_v1_api()
        nodes = api.list_node()
    except Exception:
        logger.warning("Kubernetes node monitoring failed - cluster unreachable?", exc_info=True)
        return None

    unhealthy: list[NodeStatus] = []
    for node in nodes.items:
        conditions = node.status.conditions or []
        ready = next((c for c in conditions if c.type == "Ready"), None)
        if ready is None or ready.status != "True":
            reason = (ready.reason if ready and ready.reason else None) or "NotReady"
            unhealthy.append(NodeStatus(name=node.metadata.name, reason=reason))
    return unhealthy


def list_unhealthy_containers() -> list[ContainerStatus] | None:
    """`None` when monitoring is disabled or the cluster/namespace is
    unreachable - see `list_unhealthy_nodes` for why that's never an
    empty list instead.

    Checks both `container_statuses` (the pod's main containers) and
    `init_container_statuses` - a pod stuck in `Init:CrashLoopBackOff`
    (a real, observed case in this platform's own Helm-deployed backend -
    see docs/PHASE_23.md) is crash-looping in an init container, which
    never appears in `container_statuses` at all; checking only the main
    containers would silently miss it."""
    if not is_enabled():
        return None
    settings = get_settings()
    try:
        api = _core_v1_api()
        pods = api.list_namespaced_pod(namespace=settings.KUBERNETES_NAMESPACE)
    except Exception:
        logger.warning(
            "Kubernetes container monitoring failed - cluster/namespace unreachable?", exc_info=True
        )
        return None

    unhealthy: list[ContainerStatus] = []
    for pod in pods.items:
        all_statuses = list(pod.status.container_statuses or []) + list(
            pod.status.init_container_statuses or []
        )
        for container_status in all_statuses:
            reason = None
            state = container_status.state
            if state.waiting and state.waiting.reason in _UNHEALTHY_CONTAINER_REASONS:
                reason = state.waiting.reason
            elif state.terminated and state.terminated.reason in _UNHEALTHY_CONTAINER_REASONS:
                reason = state.terminated.reason
            if reason:
                unhealthy.append(
                    ContainerStatus(
                        pod_name=pod.metadata.name,
                        container_name=container_status.name,
                        reason=reason,
                        restart_count=container_status.restart_count,
                    )
                )
    return unhealthy
