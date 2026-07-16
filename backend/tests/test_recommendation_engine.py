"""Unit tests for the pure rule-based recommendation engine (no DB needed)."""
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
