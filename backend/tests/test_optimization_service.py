"""Tests for OptimizationService, exercised directly against the DB (not
through the HTTP API) since it's triggered by the scheduler/POST
/optimization/evaluate, not by a request body.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.models.cloud_cost import CloudCost
from app.models.deployment import Deployment
from app.models.microservice import Microservice
from app.models.optimization_recommendation import OptimizationRecommendation
from app.models.prediction import Prediction
from app.models.project import Project
from app.models.resource_usage import ResourceUsage
from app.models.user import User
from app.services.optimization_service import OptimizationService


@pytest.fixture()
def demo_project_and_deployment(db_session):
    owner = User(
        username="opt_owner",
        email="opt_owner@example.com",
        full_name="Opt Owner",
        hashed_password="not-a-real-hash",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()

    project = Project(name="Optimization Demo", owner_id=owner.id)
    db_session.add(project)
    db_session.flush()

    microservice = Microservice(project_id=project.id, name="opt-service")
    db_session.add(microservice)
    db_session.flush()

    deployment = Deployment(
        microservice_id=microservice.id, name="opt-deploy", replicas=2, memory_limit_mb=1000.0
    )
    db_session.add(deployment)
    db_session.commit()
    db_session.refresh(deployment)
    return project, deployment


def _add_usage(db_session, deployment_id: int, cpu: float, memory: float, hour: int):
    db_session.add(
        ResourceUsage(
            deployment_id=deployment_id,
            cpu_usage_percent=cpu,
            memory_usage_mb=memory,
            disk_usage_mb=1000.0,
            network_in_kbps=50.0,
            network_out_kbps=30.0,
            recorded_at=datetime(2026, 7, 15, hour, 0, 0),
        )
    )
    db_session.commit()


def test_high_cpu_creates_pending_recommendation(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_created"] >= 1
    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert rec.status == "pending"


def test_high_memory_creates_recommendation_when_limit_configured(
    db_session, demo_project_and_deployment
):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=55.0, memory=950.0, hour=10)

    OptimizationService(db_session).evaluate_all()

    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_memory",
        )
        .one()
    )
    assert "950" in rec.description or "95" in rec.description


def test_rerunning_evaluation_unchanged_is_idempotent(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    service = OptimizationService(db_session)
    service.evaluate_all()
    summary_second = service.evaluate_all()

    assert summary_second["recommendations_created"] == 0

    pending = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.status == "pending",
        )
        .all()
    )
    types_seen = [r.recommendation_type for r in pending]
    assert len(types_seen) == len(set(types_seen))  # no duplicates of the same type


def test_condition_clearing_auto_dismisses_recommendation(
    db_session, demo_project_and_deployment
):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    service = OptimizationService(db_session)
    service.evaluate_all()

    _add_usage(db_session, deployment.id, cpu=60.0, memory=500.0, hour=11)
    summary = service.evaluate_all()

    assert summary["recommendations_dismissed"] >= 1
    dismissed = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert dismissed.status == "dismissed"


def test_decrease_recommendation_bundles_cost_estimate_when_cost_data_exists(
    db_session, demo_project_and_deployment
):
    project, deployment = demo_project_and_deployment
    db_session.add(
        CloudCost(
            project_id=project.id,
            provider="aws",
            service_name="EC2",
            cost_amount=2000.0,
            currency="USD",
            billing_period_start=date(2026, 6, 1),
            billing_period_end=date(2026, 6, 30),
        )
    )
    db_session.commit()
    _add_usage(db_session, deployment.id, cpu=10.0, memory=500.0, hour=10)

    OptimizationService(db_session).evaluate_all()

    cost_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "optimize_cost",
        )
        .one()
    )
    assert cost_rec.estimated_savings == pytest.approx(300.0)  # 15% of 2000


def test_decrease_recommendation_without_cost_data_has_no_estimate(
    db_session, demo_project_and_deployment
):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=10.0, memory=500.0, hour=10)

    OptimizationService(db_session).evaluate_all()

    cost_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "optimize_cost",
        )
        .one()
    )
    assert cost_rec.estimated_savings is None


def test_deployment_with_no_resource_usage_history_is_skipped(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_created"] == 0


def test_dismissed_recommendation_is_not_recreated_within_cooldown(
    db_session, demo_project_and_deployment
):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)
    OptimizationService(db_session).evaluate_all()

    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    rec.status = "dismissed"
    db_session.commit()  # updated_at becomes "now" via onupdate

    # Same triggering condition still present - without a cooldown this
    # would be recreated immediately, defeating the point of dismissing it.
    _add_usage(db_session, deployment.id, cpu=91.0, memory=500.0, hour=11)
    summary = OptimizationService(db_session).evaluate_all()

    still_none_pending = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
            OptimizationRecommendation.status == "pending",
        )
        .all()
    )
    assert still_none_pending == []
    assert summary["recommendations_created"] == 0


def _add_prediction(db_session, deployment_id: int, metric_type: str, predicted_value: float, confidence: float):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        Prediction(
            deployment_id=deployment_id,
            model_type="lstm",
            metric_type=metric_type,
            predicted_value=predicted_value,
            confidence_score=confidence,
            target_timestamp=now + timedelta(hours=1),
            generated_at=now,
        )
    )
    db_session.commit()


def test_confident_high_forecast_triggers_recommendation_actual_alone_would_not(
    db_session, demo_project_and_deployment
):
    """Actual CPU is comfortably mid-band (no threshold crossed on its own),
    but a confident LSTM forecast predicts a spike above the high
    threshold - the recommendation must still fire, proving the engine is
    genuinely forecast-informed, not only reactive to past actuals."""
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=55.0, memory=500.0, hour=10)
    _add_prediction(db_session, deployment.id, "cpu_usage_percent", predicted_value=95.0, confidence=0.9)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_created"] >= 1
    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert "LSTM forecasts" in rec.description
    assert "95.0" in rec.description


def test_low_confidence_forecast_is_ignored(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=55.0, memory=500.0, hour=10)
    _add_prediction(db_session, deployment.id, "cpu_usage_percent", predicted_value=95.0, confidence=0.2)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_created"] == 0


def test_forecast_lower_than_actual_does_not_override_or_annotate(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)
    _add_prediction(db_session, deployment.id, "cpu_usage_percent", predicted_value=50.0, confidence=0.9)

    OptimizationService(db_session).evaluate_all()

    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert "LSTM forecasts" not in rec.description


def test_recommendation_is_recreated_once_cooldown_expires(db_session, demo_project_and_deployment):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)
    OptimizationService(db_session).evaluate_all()

    rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    rec.status = "dismissed"
    rec.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=OptimizationService(db_session).settings.OPTIMIZATION_RECOMMENDATION_COOLDOWN_MINUTES + 5
    )
    db_session.commit()

    _add_usage(db_session, deployment.id, cpu=91.0, memory=500.0, hour=11)
    summary = OptimizationService(db_session).evaluate_all()

    pending = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
            OptimizationRecommendation.status == "pending",
        )
        .all()
    )
    assert len(pending) == 1
    assert summary["recommendations_created"] >= 1


# --- Auto-apply (off by default) -----------------------------------------


def test_auto_apply_disabled_by_default_leaves_recommendation_pending(
    db_session, demo_project_and_deployment
):
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_auto_applied"] == 0
    db_session.refresh(deployment)
    assert deployment.replicas == 2  # unchanged
    scale_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "scale_deployment",
        )
        .one()
    )
    assert scale_rec.status == "pending"


def test_auto_apply_enabled_updates_deployment_replicas_for_scale_deployment(
    db_session, demo_project_and_deployment, monkeypatch
):
    """cpu=90% with 2 replicas triggers both increase_pods (no numeric
    target) and scale_deployment (a concrete HPA-style target_replicas) -
    only scale_deployment is in the default auto-apply set and only it
    carries a target, so only it should actually change the deployment."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPTIMIZATION_AUTO_APPLY_ENABLED", True)
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_auto_applied"] == 1
    db_session.refresh(deployment)
    assert deployment.replicas == 3  # ceil(2 * 90/60)

    scale_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "scale_deployment",
        )
        .one()
    )
    assert scale_rec.status == "applied"
    assert "(auto-applied)" in scale_rec.description

    pods_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert pods_rec.status == "pending"  # no numeric target - never auto-applies


def test_auto_apply_enabled_updates_deployment_memory_limit(
    db_session, demo_project_and_deployment, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "OPTIMIZATION_AUTO_APPLY_ENABLED", True)
    _, deployment = demo_project_and_deployment
    # cpu held mid-band (45-75% given target 60/band 15) so only the memory
    # condition fires - isolates the memory auto-apply path.
    _add_usage(db_session, deployment.id, cpu=55.0, memory=950.0, hour=10)

    OptimizationService(db_session).evaluate_all()

    db_session.refresh(deployment)
    assert deployment.memory_limit_mb == pytest.approx(1357.1, rel=0.01)  # 950 / 0.70

    memory_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_memory",
        )
        .one()
    )
    assert memory_rec.status == "applied"


def test_auto_apply_type_in_configured_set_but_without_a_target_never_applies(
    db_session, demo_project_and_deployment, monkeypatch
):
    """Being in OPTIMIZATION_AUTO_APPLY_TYPES is necessary but not
    sufficient - increase_pods has no concrete numeric target at all, so
    even explicitly configuring it for auto-apply must not touch the
    deployment or the recommendation's status."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OPTIMIZATION_AUTO_APPLY_ENABLED", True)
    monkeypatch.setattr(settings, "OPTIMIZATION_AUTO_APPLY_TYPES", "increase_pods")
    _, deployment = demo_project_and_deployment
    _add_usage(db_session, deployment.id, cpu=90.0, memory=500.0, hour=10)

    summary = OptimizationService(db_session).evaluate_all()

    assert summary["recommendations_auto_applied"] == 0
    db_session.refresh(deployment)
    assert deployment.replicas == 2

    pods_rec = (
        db_session.query(OptimizationRecommendation)
        .filter(
            OptimizationRecommendation.deployment_id == deployment.id,
            OptimizationRecommendation.recommendation_type == "increase_pods",
        )
        .one()
    )
    assert pods_rec.status == "pending"
