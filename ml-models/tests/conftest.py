"""Pytest fixtures for the ML pipeline test suite.

Runs against a real MySQL test database (`cloud_ai_platform_ml_test`), kept
deliberately separate from the backend's own `cloud_ai_platform_test` so the
two independent projects never race on schema create/drop. The DDL here is a
simplified subset of the real Phase 1 schema (no foreign key constraints) -
enough to exercise the ML pipeline's own logic in isolation; full referential
integrity is already covered by the backend's test suite.
"""
import os

os.environ["MYSQL_DATABASE"] = "cloud_ai_platform_ml_test"

import pytest
from sqlalchemy import insert, text

from shared.db import get_engine, reflect_tables

_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS deployments (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'unknown',
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pods (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER NOT NULL,
        pod_name VARCHAR(150) NOT NULL,
        restart_count INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_usage (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER NOT NULL,
        cpu_usage_percent FLOAT NOT NULL,
        memory_usage_mb FLOAT NOT NULL,
        disk_usage_mb FLOAT NOT NULL,
        network_in_kbps FLOAT NOT NULL,
        network_out_kbps FLOAT NOT NULL,
        recorded_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER,
        pod_id INTEGER,
        metric_type VARCHAR(50) NOT NULL,
        value FLOAT NOT NULL,
        unit VARCHAR(20) NOT NULL,
        recorded_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER NOT NULL,
        model_type VARCHAR(30) NOT NULL,
        metric_type VARCHAR(50) NOT NULL,
        predicted_value FLOAT NOT NULL,
        confidence_score FLOAT NOT NULL,
        target_timestamp DATETIME NOT NULL,
        generated_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS anomaly_detections (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER NOT NULL,
        metric_type VARCHAR(50) NOT NULL,
        anomaly_score FLOAT NOT NULL,
        is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
        detected_at DATETIME NOT NULL,
        details TEXT,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS failure_predictions (
        id INTEGER AUTO_INCREMENT PRIMARY KEY,
        deployment_id INTEGER NOT NULL,
        pod_id INTEGER,
        failure_type VARCHAR(50) NOT NULL,
        probability FLOAT NOT NULL,
        predicted_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL DEFAULT NOW(),
        updated_at DATETIME NOT NULL DEFAULT NOW() ON UPDATE NOW()
    )
    """,
]

_TABLE_NAMES_DROP_ORDER = [
    "failure_predictions",
    "anomaly_detections",
    "predictions",
    "metrics",
    "resource_usage",
    "pods",
    "deployments",
]


@pytest.fixture(scope="session")
def engine():
    eng = get_engine()
    with eng.begin() as conn:
        for statement in _DDL_STATEMENTS:
            conn.execute(text(statement))
    yield eng
    with eng.begin() as conn:
        for table_name in _TABLE_NAMES_DROP_ORDER:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))


@pytest.fixture()
def tables(engine):
    return reflect_tables(engine)


@pytest.fixture()
def deployment_and_pod(engine, tables):
    with engine.begin() as conn:
        deployment_id = conn.execute(
            insert(tables["deployments"]).values(name="test-deploy", status="running")
        ).inserted_primary_key[0]
        pod_id = conn.execute(
            insert(tables["pods"]).values(
                deployment_id=deployment_id, pod_name="test-pod-1", restart_count=0
            )
        ).inserted_primary_key[0]

    yield deployment_id, pod_id

    with engine.begin() as conn:
        for table_name in ["failure_predictions", "anomaly_detections", "predictions", "metrics", "resource_usage"]:
            conn.execute(
                tables[table_name].delete().where(tables[table_name].c.deployment_id == deployment_id)
            )
        conn.execute(tables["pods"].delete().where(tables["pods"].c.id == pod_id))
        conn.execute(tables["deployments"].delete().where(tables["deployments"].c.id == deployment_id))
