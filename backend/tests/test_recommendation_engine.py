"""Unit tests for the pure rule-based recommendation engine (no DB needed)."""
import pytest

from app.optimization.recommendation_engine import evaluate


def _types(conditions):
    return {c.recommendation_type for c in conditions}


def test_high_cpu_with_room_to_scale_recommends_increase_pods():
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=500.0, memory_limit_mb=None, replicas=2
    )
    assert "increase_pods" in _types(conditions)
    assert "increase_cpu" not in _types(conditions)


def test_high_cpu_at_scaling_ceiling_recommends_increase_cpu():
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=500.0, memory_limit_mb=None, replicas=10
    )
    assert "increase_cpu" in _types(conditions)
    assert "increase_pods" not in _types(conditions)


def test_low_cpu_with_multiple_replicas_recommends_reduce_pods():
    conditions = evaluate(
        avg_cpu_usage_percent=10.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=4
    )
    assert "reduce_pods" in _types(conditions)
    assert "reduce_cpu" not in _types(conditions)


def test_low_cpu_with_single_replica_recommends_reduce_cpu():
    conditions = evaluate(
        avg_cpu_usage_percent=10.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=1
    )
    assert "reduce_cpu" in _types(conditions)
    assert "reduce_pods" not in _types(conditions)


def test_moderate_cpu_recommends_nothing_cpu_related():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=2
    )
    cpu_types = {"increase_cpu", "reduce_cpu", "increase_pods", "reduce_pods"}
    assert not (cpu_types & _types(conditions))


def test_memory_recommendations_require_a_configured_limit():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=950.0, memory_limit_mb=None, replicas=2
    )
    assert "increase_memory" not in _types(conditions)


def test_high_memory_utilization_recommends_increase_memory():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=950.0, memory_limit_mb=1000.0, replicas=2
    )
    assert "increase_memory" in _types(conditions)


def test_low_memory_utilization_recommends_reduce_memory():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=50.0, memory_limit_mb=1000.0, replicas=2
    )
    assert "reduce_memory" in _types(conditions)


def test_scale_deployment_gives_hpa_style_target_replica_count():
    # HPA formula: desired = ceil(current * currentUtil / targetUtil) = ceil(2 * 90/60) = 3
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=2
    )
    scale_conditions = [c for c in conditions if c.recommendation_type == "scale_deployment"]
    assert len(scale_conditions) == 1
    assert "3" in scale_conditions[0].description
    assert scale_conditions[0].direction == "increase"


def test_scale_deployment_direction_is_decrease_when_target_replicas_lower():
    # desired = ceil(4 * 10/60) = ceil(0.67) = 1
    conditions = evaluate(
        avg_cpu_usage_percent=10.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=4
    )
    scale_conditions = [c for c in conditions if c.recommendation_type == "scale_deployment"]
    assert len(scale_conditions) == 1
    assert scale_conditions[0].direction == "decrease"


def test_cpu_within_target_band_does_not_recommend_scaling():
    conditions = evaluate(
        avg_cpu_usage_percent=60.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=3
    )
    assert "scale_deployment" not in _types(conditions)


def test_scale_deployment_desired_replicas_is_capped_at_max_scale_replicas():
    # Uncapped HPA formula: ceil(5 * 200/60) = 17 - a safety limit must clamp
    # this to OPTIMIZATION_MAX_SCALE_REPLICAS (default 10), never suggesting
    # scaling to an unbounded replica count off the back of a CPU spike.
    conditions = evaluate(
        avg_cpu_usage_percent=200.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=5
    )
    scale_conditions = [c for c in conditions if c.recommendation_type == "scale_deployment"]
    assert len(scale_conditions) == 1
    assert "to 10 replica" in scale_conditions[0].description
    assert "to 17 replica" not in scale_conditions[0].description


# --- Concrete numeric targets (used by OptimizationService's auto-apply) --


def test_scale_deployment_carries_a_concrete_target_replicas():
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=2
    )
    scale_condition = next(c for c in conditions if c.recommendation_type == "scale_deployment")
    assert scale_condition.target_replicas == 3
    assert scale_condition.target_memory_limit_mb is None


def test_increase_pods_carries_no_concrete_target():
    """Purely qualitative - there is no single "correct" replica count for
    a horizontal scale-out beyond what scale_deployment already computes,
    so this must never carry a target that would let it silently
    auto-apply."""
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=2
    )
    pods_condition = next(c for c in conditions if c.recommendation_type == "increase_pods")
    assert pods_condition.target_replicas is None
    assert pods_condition.target_memory_limit_mb is None


def test_increase_memory_carries_a_concrete_target_memory_limit():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=950.0, memory_limit_mb=1000.0, replicas=2
    )
    memory_condition = next(c for c in conditions if c.recommendation_type == "increase_memory")
    assert memory_condition.target_memory_limit_mb == pytest.approx(1357.1, rel=0.01)  # 950 / 0.70
    assert memory_condition.target_replicas is None


def test_reduce_memory_carries_a_concrete_target_memory_limit():
    conditions = evaluate(
        avg_cpu_usage_percent=55.0, avg_memory_usage_mb=50.0, memory_limit_mb=1000.0, replicas=2
    )
    memory_condition = next(c for c in conditions if c.recommendation_type == "reduce_memory")
    assert memory_condition.target_memory_limit_mb == pytest.approx(71.43, rel=0.01)  # 50 / 0.70


def test_increase_cpu_carries_no_concrete_target():
    """No CPU-limit field exists on Deployment to write a target onto."""
    conditions = evaluate(
        avg_cpu_usage_percent=90.0, avg_memory_usage_mb=100.0, memory_limit_mb=None, replicas=10
    )
    cpu_condition = next(c for c in conditions if c.recommendation_type == "increase_cpu")
    assert cpu_condition.target_replicas is None
    assert cpu_condition.target_memory_limit_mb is None
