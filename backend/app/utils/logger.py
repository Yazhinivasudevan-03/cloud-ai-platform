"""Application-wide logging configuration.

Emits one JSON object per line (Phase 19) rather than a human-formatted
line, so a real log aggregator (ELK/Loki/CloudWatch Logs Insights) can
query on individual fields - `level`, `logger`, `message`, and, when a
request is being traced, `trace_id`/`span_id` - instead of grepping
formatted text. The trace/span IDs let a specific log line be correlated
back to the exact distributed trace it was emitted during (see
app/observability/tracing.py) - genuinely useful only once tracing is
enabled, but harmless (simply absent) otherwise.
"""
import json
import logging
import sys

from opentelemetry import trace

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")

        # Any caller-supplied structured fields (logger.info(..., extra={...}))
        # are passed through as their own top-level JSON keys rather than
        # flattened into the message string.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(debug: bool = False) -> None:
    """Configure the root logger once at application startup."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
