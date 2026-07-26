"""Thin HTTP client for this platform's own Prometheus instance (Phase 23).

Queries the same `http_request_duration_seconds`/`http_requests_total`
metrics `prometheus-fastapi-instrumentator` has exposed at `/metrics`
since Phase 3/18 (see app/monitoring/prometheus_metrics.py) - never a
second, independent metrics pipeline. Used by AlertEvaluationService's
API Latency/Error Rate evaluators.

Every function returns `None` (never 0, never a fabricated value) when
Prometheus is unreachable or there is no traffic to compute a rate from
yet - callers must treat `None` as "skip this evaluation", the same
guard every other real evaluator in this platform already uses for
"not enough data configured/collected yet".
"""
import httpx

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger("integrations.prometheus")

_JOB = "cloud-ai-backend"


def _instant_query(promql: str) -> float | None:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.PROMETHEUS_URL}/api/v1/query", params={"query": promql}, timeout=2
        )
        response.raise_for_status()
        result = response.json()["data"]["result"]
        if not result:
            return None
        return float(result[0]["value"][1])
    except Exception:
        logger.warning("Prometheus query failed or unreachable: %s", promql, exc_info=True)
        return None


def average_latency_ms(window: str = "5m") -> float | None:
    """Average HTTP request latency across every endpoint, in
    milliseconds, over the trailing `window`. `None` when there is no
    request traffic in that window to average (rather than fabricating
    0ms - a service with zero requests has no observed latency)."""
    total_count = _instant_query(f'sum(rate(http_request_duration_seconds_count{{job="{_JOB}"}}[{window}]))')
    if not total_count:
        return None
    total_time = _instant_query(f'sum(rate(http_request_duration_seconds_sum{{job="{_JOB}"}}[{window}]))')
    return ((total_time or 0.0) / total_count) * 1000


def error_rate_percent(window: str = "5m") -> float | None:
    """Percentage of requests returning a 5xx status over the trailing
    `window`. `None` when there is no traffic at all (can't compute a
    rate); a real 0.0 when there is traffic but no 5xx responses - these
    are two different, both-real outcomes, not conflated into one."""
    total = _instant_query(f'sum(rate(http_requests_total{{job="{_JOB}"}}[{window}]))')
    if not total:
        return None
    errors = _instant_query(f'sum(rate(http_requests_total{{job="{_JOB}", status="5xx"}}[{window}]))')
    return ((errors or 0.0) / total) * 100
