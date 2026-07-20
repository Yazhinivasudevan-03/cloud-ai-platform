"""Registers the periodic real-time-cloud-metrics-sync job onto the shared
scheduler (see app/scheduler.py) - the mechanism that actually makes cloud
data flow into the platform continuously, rather than only on an operator's
manual "sync now" request (POST /deployments/{id}/sync-cloud-metrics)."""
from apscheduler.schedulers.background import BackgroundScheduler

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.services.cloud_sync_service import CloudSyncService
from app.utils.logger import get_logger

logger = get_logger("cloud_sync.scheduler")


def _run_sync_all() -> None:
    db = SessionLocal()
    try:
        summary = CloudSyncService(db).sync_all()
        logger.info("Scheduled cloud metrics sync: %s", summary)
    except Exception:
        logger.exception("Scheduled cloud metrics sync failed")
    finally:
        db.close()


def register_cloud_sync_job(scheduler: BackgroundScheduler) -> None:
    settings = get_settings()
    scheduler.add_job(
        _run_sync_all,
        "interval",
        minutes=settings.CLOUD_SYNC_INTERVAL_MINUTES,
        id="cloud_metrics_sync",
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Cloud metrics sync job registered (every %s minutes)",
        settings.CLOUD_SYNC_INTERVAL_MINUTES,
    )
