"""FastAPI application factory and entrypoint.

Run locally with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.scheduler import register_alert_evaluation_job
from app.config.settings import get_settings
from app.middleware.error_handler import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.rate_limiter import register_rate_limiter
from app.monitoring.prometheus_metrics import register_prometheus_metrics
from app.optimization.scheduler import register_optimization_evaluation_job
from app.routers import (
    alert_router,
    auth_router,
    cloud_cost_router,
    deployment_router,
    health_router,
    metric_router,
    microservice_router,
    notification_router,
    optimization_router,
    pod_router,
    prediction_router,
    project_router,
    user_router,
)
from app.scheduler import create_scheduler, shutdown_scheduler
from app.utils.logger import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    register_alert_evaluation_job(scheduler)
    register_optimization_evaluation_job(scheduler)
    scheduler.start()
    yield
    shutdown_scheduler(scheduler)


def create_app() -> FastAPI:
    configure_logging(debug=settings.DEBUG)

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization "
            "Platform for Microservices - REST API"
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    register_rate_limiter(app)
    register_exception_handlers(app)
    register_prometheus_metrics(app)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router.router)
    app.include_router(auth_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(user_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(project_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(microservice_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(deployment_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(pod_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(metric_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(prediction_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(alert_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(notification_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(optimization_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(cloud_cost_router.router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
