"""Prometheus instrumentation for the FastAPI application.

Exposes a `/metrics` endpoint (Prometheus exposition format) carrying
standard HTTP server metrics - `http_requests_total` (counter, labeled by
method/handler/status) and `http_request_duration_seconds` (histogram,
labeled by method/handler) - which the platform's own Prometheus instance
scrapes (see monitoring/prometheus/prometheus.yml, job "cloud-ai-backend").
This is what feeds the "API Response Time"/"Availability"/"Latency" panels
on the Grafana "Cloud AI Platform - Overview" dashboard.
"""
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def register_prometheus_metrics(app: FastAPI) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
