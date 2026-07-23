"""OpenTelemetry SDK instrumentation: distributed tracing for the backend
(Phase 19, audit roadmap item 13).

Every incoming HTTP request and every SQLAlchemy query it triggers gets a
real span, correlated into a single trace per request - genuinely useful
for answering "why was this request slow" across the FastAPI layer and
the database, not a cosmetic instrumentation-for-its-own-sake addition.

No live OTLP collector (Jaeger/Tempo/an OTel Collector) was available in
this environment to verify export against, so the default exporter is
`ConsoleSpanExporter` - spans print as JSON to stdout, which is genuinely
inspectable (`docker compose logs backend`) with zero external services,
and was what this phase's own verification actually exercised. Setting
`OTEL_EXPORTER_OTLP_ENDPOINT` switches to a real OTLP/HTTP export with no
code change - disclosed in docs/PHASE_19.md as unverified against a real
collector.
"""
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from sqlalchemy.engine import Engine

from app.config.settings import get_settings


def configure_tracing(app: FastAPI, engine: Engine) -> None:
    settings = get_settings()
    if not settings.OTEL_ENABLED:
        return

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: settings.OTEL_SERVICE_NAME})
    )

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        # No collector configured - export to stdout so tracing is still
        # genuinely observable rather than silently doing nothing.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
