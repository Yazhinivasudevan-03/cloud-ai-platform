"""Registers the periodic resource-optimization-evaluation job onto the
shared scheduler (see app/scheduler.py). Runs less frequently than alerts by
default (60 minutes vs 5) since recommendations are about sustained
utilization trends, not time-sensitive incidents.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from app.config.settings import get_settings
from app.database.session import SessionLocal
from app.services.optimization_service import OptimizationService
from app.utils.logger import get_logger

logger = get_logger("optimization.scheduler")


def _run_evaluation() -> None:
    db = SessionLocal()
    try:
        summary = OptimizationService(db).evaluate_all()
        logger.info("Scheduled optimization evaluation: %s", summary)
    except Exception:
        logger.exception("Scheduled optimization evaluation failed")
    finally:
        db.close()


def register_optimization_evaluation_job(scheduler: BackgroundScheduler) -> None:
    settings = get_settings()
    scheduler.add_job(
        _run_evaluation,
        "interval",
        minutes=settings.OPTIMIZATION_EVALUATION_INTERVAL_MINUTES,
        id="optimization_evaluation",
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Optimization evaluation job registered (every %s minutes)",
        settings.OPTIMIZATION_EVALUATION_INTERVAL_MINUTES,
    )
