"""Registers the periodic alert-evaluation job onto the shared scheduler.

Runs inside the FastAPI process itself (APScheduler, its own thread) rather
than as a separate container - the evaluation query is cheap (a handful of
`SELECT ... ORDER BY ... LIMIT 1` per deployment) and doesn't warrant a
dedicated service. `POST /alerts/evaluate` (see app/routers/alert_router.py)
runs the exact same `AlertEvaluationService` on demand, for manual
triggering/demoing without waiting for the interval.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.services.alert_evaluation_service import AlertEvaluationService
from app.utils.logger import get_logger

logger = get_logger("alerts.scheduler")


def _run_evaluation() -> None:
    db = SessionLocal()
    try:
        summary = AlertEvaluationService(db).evaluate_all()
        logger.info("Scheduled alert evaluation: %s", summary)
    except Exception:
        logger.exception("Scheduled alert evaluation failed")
    finally:
        db.close()


def register_alert_evaluation_job(scheduler: BackgroundScheduler) -> None:
    settings = get_settings()
    scheduler.add_job(
        _run_evaluation,
        "interval",
        minutes=settings.ALERT_EVALUATION_INTERVAL_MINUTES,
        id="alert_evaluation",
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Alert evaluation job registered (every %s minutes)",
        settings.ALERT_EVALUATION_INTERVAL_MINUTES,
    )
