"""Pure rule-based resource optimization recommendation engine.

Takes already-aggregated utilization figures - this module has no DB access
at all - and returns the set of currently-applicable recommendations. Kept
separate from `OptimizationService` (which handles the DB round trip, the
dedup/auto-dismiss lifecycle, and cost estimation) so the actual decision
logic is trivially unit-testable without a database.

CPU vs pods: a high-CPU deployment gets an `increase_pods` (horizontal scale
out) recommendation while it still has headroom under
`OPTIMIZATION_MAX_SCALE_REPLICAS`, and only falls back to `increase_cpu`
(vertical) once it's already scaled out as far as reasonable - horizontal
scaling is the standard Kubernetes-native lever, so it's preferred. The
inverse applies for low CPU: scale in (`reduce_pods`) while there's more than
one replica to remove, otherwise `reduce_cpu`.

`scale_deployment` is deliberately a *quantitative* companion to
`increase_pods`/`reduce_pods`, not a replacement for them: it applies the
exact formula Kubernetes' own Horizontal Pod Autoscaler uses -
`desiredReplicas = ceil(currentReplicas * currentUtilization / targetUtilization)`
- giving a specific target replica count alongside the categorical
recommendation.
"""
from dataclasses import dataclass
from math import ceil

from app.config.settings import get_settings


@dataclass(frozen=True)
class RecommendationCondition:
    recommendation_type: str
    description: str
    direction: str  # "increase" or "decrease" - lets the cost step know whether this implies savings


def evaluate(
    avg_cpu_usage_percent: float,
    avg_memory_usage_mb: float | None,
    memory_limit_mb: float | None,
    replicas: int,
) -> list[RecommendationCondition]:
    settings = get_settings()
    conditions: list[RecommendationCondition] = []

    if avg_cpu_usage_percent >= settings.OPTIMIZATION_CPU_HIGH_THRESHOLD:
        if replicas >= settings.OPTIMIZATION_MAX_SCALE_REPLICAS:
            conditions.append(
                RecommendationCondition(
                    "increase_cpu",
                    f"Average CPU usage is {avg_cpu_usage_percent:.1f}% and replica "
                    f"count ({replicas}) is already at the practical scaling ceiling "
                    f"({settings.OPTIMIZATION_MAX_SCALE_REPLICAS}) - increase the CPU "
                    f"allocation per pod instead of scaling out further.",
                    "increase",
                )
            )
        else:
            conditions.append(
                RecommendationCondition(
                    "increase_pods",
                    f"Average CPU usage is {avg_cpu_usage_percent:.1f}% with "
                    f"{replicas} replica(s) - scale out (add pods) to spread the load.",
                    "increase",
                )
            )
    elif avg_cpu_usage_percent <= settings.OPTIMIZATION_CPU_LOW_THRESHOLD:
        if replicas > 1:
            conditions.append(
                RecommendationCondition(
                    "reduce_pods",
                    f"Average CPU usage is only {avg_cpu_usage_percent:.1f}% across "
                    f"{replicas} replicas - scale in to reduce idle capacity.",
                    "decrease",
                )
            )
        else:
            conditions.append(
                RecommendationCondition(
                    "reduce_cpu",
                    f"Average CPU usage is only {avg_cpu_usage_percent:.1f}% on a "
                    f"single replica - reduce the CPU allocation per pod.",
                    "decrease",
                )
            )

    if memory_limit_mb and memory_limit_mb > 0 and avg_memory_usage_mb is not None:
        memory_percent = (avg_memory_usage_mb / memory_limit_mb) * 100
        if memory_percent >= settings.OPTIMIZATION_MEMORY_HIGH_THRESHOLD:
            conditions.append(
                RecommendationCondition(
                    "increase_memory",
                    f"Average memory usage is {memory_percent:.1f}% of the "
                    f"configured {memory_limit_mb:.0f}MB limit - increase the "
                    f"memory allocation.",
                    "increase",
                )
            )
        elif memory_percent <= settings.OPTIMIZATION_MEMORY_LOW_THRESHOLD:
            conditions.append(
                RecommendationCondition(
                    "reduce_memory",
                    f"Average memory usage is only {memory_percent:.1f}% of the "
                    f"configured {memory_limit_mb:.0f}MB limit - reduce the memory "
                    f"allocation.",
                    "decrease",
                )
            )

    target = settings.OPTIMIZATION_TARGET_CPU_PERCENT
    band = settings.OPTIMIZATION_TARGET_CPU_BAND
    if avg_cpu_usage_percent > target + band or avg_cpu_usage_percent < target - band:
        # Safety limit: never recommend below 1 replica or above the same
        # practical ceiling the increase_pods/increase_cpu branch above
        # already respects - a runaway CPU spike shouldn't be able to
        # produce a recommendation to scale to an unbounded replica count.
        desired_replicas = max(
            1,
            min(settings.OPTIMIZATION_MAX_SCALE_REPLICAS, ceil(replicas * (avg_cpu_usage_percent / target))),
        )
        if desired_replicas != replicas:
            conditions.append(
                RecommendationCondition(
                    "scale_deployment",
                    f"HPA-style target: scale from {replicas} to {desired_replicas} "
                    f"replica(s) to bring average CPU from "
                    f"{avg_cpu_usage_percent:.1f}% towards the {target:.0f}% target.",
                    "decrease" if desired_replicas < replicas else "increase",
                )
            )

    return conditions
