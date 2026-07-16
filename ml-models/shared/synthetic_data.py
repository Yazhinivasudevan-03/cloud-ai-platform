"""Synthetic resource-usage/incident data generator for demo & model training.

THIS DATA IS SYNTHETIC. There is no production traffic on this platform yet
(the platform itself is still being built phase by phase), so this generator
exists purely to give the Phase 4 models something realistic to train
against: daily seasonality, gradual memory drift, and periodic "stress
episodes" that precede a synthetic pod restart a few hours later - the same
leading-indicator structure a real incident would have, so the Random Forest
model has genuine predictive signal to learn rather than fitting to noise.

Restart events are recorded as `metrics` rows with metric_type="pod_restart"
(value=1, unit="count") rather than requiring a new database table - the
generic Metric model designed in Phase 1 is exactly the flexible time-series
event store this needs.
"""
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, update
from sqlalchemy.engine import Engine

RESTART_METRIC_TYPE = "pod_restart"


def generate(
    engine: Engine,
    tables: dict,
    deployment_id: int,
    pod_id: int,
    days: int = 21,
    seed: int = 42,
) -> dict:
    """Backfill `days` of hourly resource_usage history ending now, with
    periodic stress episodes that precede a pod_restart metric event.
    Returns a summary dict describing what was inserted.
    """
    rng = random.Random(seed)
    resource_usage = tables["resource_usage"]
    metrics = tables["metrics"]
    pods = tables["pods"]

    now = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    hours = int((now - start).total_seconds() // 3600)

    # Roughly one stress episode every ~3.5 days, each lasting 3-6 hours.
    episode_gap = 84
    incidents: list[tuple[int, int]] = []
    hour = rng.randint(24, episode_gap)
    while hour < hours:
        duration = rng.randint(3, 6)
        incidents.append((hour, hour + duration))
        hour += episode_gap + rng.randint(-12, 12)

    resource_rows = []
    restart_events: list[datetime] = []
    memory_baseline = 400.0
    disk_baseline = 2000.0

    for h in range(hours):
        ts = start + timedelta(hours=h)
        hour_of_day = ts.hour
        in_episode = any(s <= h < e for s, e in incidents)

        # A restart lands 2-4 hours after each episode's last stressed hour.
        for _, e in incidents:
            if h == e + rng.randint(2, 4):
                restart_events.append(ts)

        daily_cpu = 35 + 15 * math.sin(2 * math.pi * (hour_of_day - 6) / 24)
        cpu = daily_cpu + rng.gauss(0, 4)
        if in_episode:
            cpu += rng.uniform(35, 55)
        cpu = max(1.0, min(100.0, cpu))

        memory_baseline += rng.uniform(0.5, 2.0)  # slow drift, simulating a leak
        if h > 0 and h % 24 == 0:
            memory_baseline *= 0.97  # partial nightly relief (e.g. periodic GC)
        memory = memory_baseline + rng.gauss(0, 10)
        if in_episode:
            memory += rng.uniform(150, 300)
        memory = max(100.0, memory)

        disk_baseline += rng.uniform(0.2, 0.8)
        disk = disk_baseline + rng.gauss(0, 5)

        daily_net = 80 + 40 * math.sin(2 * math.pi * (hour_of_day - 9) / 24)
        net_in = max(1.0, daily_net + rng.gauss(0, 10) + (30 if in_episode else 0))
        net_out = max(1.0, daily_net * 0.6 + rng.gauss(0, 8) + (20 if in_episode else 0))

        resource_rows.append(
            {
                "deployment_id": deployment_id,
                "cpu_usage_percent": round(cpu, 2),
                "memory_usage_mb": round(memory, 2),
                "disk_usage_mb": round(disk, 2),
                "network_in_kbps": round(net_in, 2),
                "network_out_kbps": round(net_out, 2),
                "recorded_at": ts,
            }
        )

    with engine.begin() as conn:
        if resource_rows:
            conn.execute(insert(resource_usage), resource_rows)

        metric_rows = [
            {
                "deployment_id": deployment_id,
                "pod_id": pod_id,
                "metric_type": RESTART_METRIC_TYPE,
                "value": 1.0,
                "unit": "count",
                "recorded_at": ts,
            }
            for ts in restart_events
        ]
        if metric_rows:
            conn.execute(insert(metrics), metric_rows)

        if restart_events:
            conn.execute(
                update(pods)
                .where(pods.c.id == pod_id)
                .values(restart_count=pods.c.restart_count + len(restart_events))
            )

    return {
        "rows_inserted": len(resource_rows),
        "incidents": len(incidents),
        "restart_events": len(restart_events),
        "period_start": start,
        "period_end": now,
    }
