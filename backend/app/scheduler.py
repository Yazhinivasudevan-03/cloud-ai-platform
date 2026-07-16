"""One shared APScheduler instance for the whole application.

Both the alert rule engine (Phase 5) and the resource-optimization rule
engine (Phase 6) need to run periodically. Rather than each owning its own
`BackgroundScheduler` (two extra threads doing the same job-scheduling work),
they each register a job onto this single shared instance, created once in
`app.main`'s lifespan handler.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from app.utils.logger import get_logger

logger = get_logger("scheduler")


def create_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler(timezone="UTC")


def shutdown_scheduler(scheduler: BackgroundScheduler) -> None:
    scheduler.shutdown(wait=False)
