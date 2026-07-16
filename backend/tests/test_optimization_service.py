"""Tests for OptimizationService, exercised directly against the DB (not
through the HTTP API) since it's triggered by the scheduler/POST
/optimization/evaluate, not by a request body.
"""
from datetime import date, datetime

import pytest

from app.models.cloud_cost import CloudCost
from app.models.deployment import Deployment
from app.models.microservice import Microservice
from app.models.optimization_recommendation import OptimizationRecommendation
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
