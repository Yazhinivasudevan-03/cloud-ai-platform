"""Shared data-loading helpers used by all three model pipelines."""
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine

from shared.synthetic_data import RESTART_METRIC_TYPE


def load_resource_usage(engine: Engine, tables: dict, deployment_id: int) -> pd.DataFrame:
    """Return resource_usage history for a deployment, sorted by time, as a
    DataFrame indexed by `recorded_at`."""
    resource_usage = tables["resource_usage"]
    stmt = (
        select(
            resource_usage.c.recorded_at,
            resource_usage.c.cpu_usage_percent,
            resource_usage.c.memory_usage_mb,
            resource_usage.c.disk_usage_mb,
            resource_usage.c.network_in_kbps,
            resource_usage.c.network_out_kbps,
        )
        .where(resource_usage.c.deployment_id == deployment_id)
        .order_by(resource_usage.c.recorded_at)
    )
    with engine.connect() as conn:
        df = pd.read_sql_query(stmt, conn)
    df = df.set_index("recorded_at")
    return df


def load_restart_events(engine: Engine, tables: dict, deployment_id: int) -> list[datetime]:
    """Return timestamps of synthetic pod_restart events for a deployment."""
    metrics = tables["metrics"]
    stmt = select(metrics.c.recorded_at).where(
        metrics.c.deployment_id == deployment_id,
        metrics.c.metric_type == RESTART_METRIC_TYPE,
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).scalars().all()
    return sorted(rows)
