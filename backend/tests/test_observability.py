"""Tests for structured JSON logging and OpenTelemetry tracing (Phase 19,
audit roadmap item 13).

The rest of the test suite runs with OTEL_ENABLED=false (see conftest.py)
so its many HTTP requests don't each also print a span to stdout - this
file is where the tracing code itself is actually exercised, against
throwaway FastAPI apps/engines, never the real app.main.app singleton.
"""
import json
import logging
import sys
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine

from app.config.settings import get_settings
from app.observability.tracing import configure_tracing
from app.utils.logger import JsonFormatter

# --- Structured JSON logging --------------------------------------------


def _make_record(**overrides) -> logging.LogRecord:
    defaults = dict(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    defaults.update(overrides)
    return logging.LogRecord(**defaults)


def test_json_formatter_produces_valid_json_with_expected_fields():
    output = JsonFormatter().format(_make_record())
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "hello world"
    assert "trace_id" not in parsed  # no active span outside a traced request


def test_json_formatter_passes_through_extra_fields():
    record = _make_record(msg="hi", args=())
    record.request_id = "abc-123"

    parsed = json.loads(JsonFormatter().format(record))

    assert parsed["request_id"] == "abc-123"


def test_json_formatter_includes_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(level=logging.ERROR, msg="failed", args=(), exc_info=sys.exc_info())

    parsed = json.loads(JsonFormatter().format(record))

    assert "exception" in parsed
    assert "ValueError: boom" in parsed["exception"]


def test_json_formatter_includes_trace_and_span_id_when_a_span_is_active():
    # A tracer obtained directly from a local TracerProvider still sets
    # real context (trace.get_current_span() reads from OpenTelemetry's
    # context API, independent of which provider is registered globally),
    # so this is isolated from the global-tracer-provider-is-a-singleton
    # constraint the tests below have to work around.
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("test-span"):
        parsed = json.loads(JsonFormatter().format(_make_record(msg="inside a span", args=())))

    assert len(parsed["trace_id"]) == 32
    assert len(parsed["span_id"]) == 16


# --- OpenTelemetry tracing setup -----------------------------------------


def test_configure_tracing_is_a_no_op_when_disabled(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "OTEL_ENABLED", False)

    test_app = FastAPI()
    test_engine = create_engine("sqlite:///:memory:")

    with patch("app.observability.tracing.FastAPIInstrumentor") as mock_instrumentor:
        configure_tracing(test_app, test_engine)

    mock_instrumentor.instrument_app.assert_not_called()


def test_configure_tracing_uses_otlp_exporter_when_endpoint_configured(monkeypatch):
    """Verified via a mocked exporter constructor, not a real global
    provider swap - `trace.set_tracer_provider` only ever takes effect
    once per process, so a second real call in this same test session
    (after the request-tracing test below) would silently be ignored by
    the SDK. Mocking the exporter class sidesteps that entirely: this
    only checks configure_tracing *chooses* the OTLP exporter and
    constructs it with the right endpoint when one is configured."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OTEL_ENABLED", True)
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")

    test_app = FastAPI()
    test_engine = create_engine("sqlite:///:memory:")

    with patch("app.observability.tracing.OTLPSpanExporter") as mock_otlp_exporter_cls:
        configure_tracing(test_app, test_engine)

    mock_otlp_exporter_cls.assert_called_once_with(endpoint="http://otel-collector:4318/v1/traces")

    FastAPIInstrumentor.uninstrument_app(test_app)
    SQLAlchemyInstrumentor().uninstrument(engine=test_engine)


def test_configure_tracing_creates_a_real_span_for_each_request(monkeypatch):
    """The one test in this file allowed to let configure_tracing actually
    win the global TracerProvider slot (console-exporter path, no OTLP
    endpoint configured) - proves a real request through an instrumented
    FastAPI app produces a real, finished span, not just that the setup
    code runs without raising."""
    settings = get_settings()
    monkeypatch.setattr(settings, "OTEL_ENABLED", True)
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")

    test_app = FastAPI()

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    test_engine = create_engine("sqlite:///:memory:")

    configure_tracing(test_app, test_engine)

    # Attach an in-memory exporter to whatever provider configure_tracing
    # just installed, to inspect spans without parsing stdout - adding a
    # span processor (unlike replacing the provider itself) is allowed any
    # number of times.
    memory_exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(memory_exporter))

    with TestClient(test_app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    spans = memory_exporter.get_finished_spans()
    assert len(spans) >= 1

    FastAPIInstrumentor.uninstrument_app(test_app)
    SQLAlchemyInstrumentor().uninstrument(engine=test_engine)
