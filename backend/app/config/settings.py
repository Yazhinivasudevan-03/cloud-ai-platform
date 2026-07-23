"""Centralized application configuration loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings. All values can be overridden via environment
    variables or a `.env` file at the backend project root."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "Cloud AI Platform"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # MySQL
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "cloudai"
    MYSQL_PASSWORD: str = "cloudai_password"
    MYSQL_DATABASE: str = "cloud_ai_platform"
    MYSQL_ROOT_PASSWORD: str = "root_password"

    # A separate database (same MySQL server) holding only login credentials
    # (users/roles/user_roles) - isolated from the rest of the application
    # data so a compromise or backup/restore of the main application
    # database never exposes or touches password hashes. See docs/PHASE_13.md.
    AUTH_MYSQL_DATABASE: str = "cloud_ai_auth"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cloud provider account credential encryption (see app/utils/crypto.py) -
    # deliberately a separate secret from SECRET_KEY: the JWT signing key and
    # the at-rest encryption key for stored cloud credentials serve different
    # cryptographic purposes and should never be the same value, so that
    # rotating one never silently weakens or breaks the other.
    CLOUD_CREDENTIALS_ENCRYPTION_KEY: str = "change-me-cloud-credentials-key-in-production"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Rate limiting - previously only login/register were throttled at all;
    # broadened per the technical audit's finding that every other endpoint,
    # including expensive ones, was completely unthrottled.
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "10/hour"
    RATE_LIMIT_REFRESH: str = "20/minute"
    # Full batch evaluation across every deployment - expensive, and already
    # runs automatically on a schedule, so manual triggers don't need to be
    # frequent.
    RATE_LIMIT_EVALUATION: str = "10/hour"
    # Calls a real external cloud provider API (AWS CloudWatch) - throttled
    # independently of the account/deployment "no restriction on count"
    # features (Phase 11/12), which limit total resources, not request rate.
    RATE_LIMIT_CLOUD_SYNC: str = "30/hour"
    # Resource usage ingestion - generous, since a real monitored deployment
    # may legitimately post readings often, but still bounded against abuse.
    RATE_LIMIT_INGESTION: str = "120/minute"
    # Sends real messages through paid/rate-limited third-party APIs
    # (Twilio SMS, Telegram, Slack) - deliberately tight so "Test
    # Notification" can't be used to spam a channel or run up an SMS bill.
    RATE_LIMIT_NOTIFICATION_TEST: str = "5/hour"

    # Alerting
    ALERT_EVALUATION_INTERVAL_MINUTES: int = 5
    ALERT_CPU_WARNING_THRESHOLD: float = 60.0
    ALERT_CPU_CRITICAL_THRESHOLD: float = 80.0
    ALERT_CPU_SATURATED_THRESHOLD: float = 100.0
    # Memory alerting (Phase 20) - previously memory_usage_mb was only used
    # by OptimizationService's recommendations, never turned into a real
    # Alert. New, so uses the exact 60/80/90 tiers requested rather than
    # inheriting CPU's historical 60/80/100 (CPU's saturated=100 predates
    # this and is left unchanged to avoid altering already-tested behavior).
    ALERT_MEMORY_WARNING_THRESHOLD: float = 60.0
    ALERT_MEMORY_CRITICAL_THRESHOLD: float = 80.0
    ALERT_MEMORY_SATURATED_THRESHOLD: float = 90.0
    ALERT_FAILURE_WARNING_THRESHOLD: float = 0.5
    ALERT_FAILURE_CRITICAL_THRESHOLD: float = 0.8

    # Notification channels - each defaults to "unconfigured" (falls back to
    # logging instead of real delivery; see app/notifications/*_notifier.py)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""
    SMTP_USE_TLS: bool = True
    SLACK_WEBHOOK_URL: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Resource optimization
    OPTIMIZATION_EVALUATION_INTERVAL_MINUTES: int = 60
    OPTIMIZATION_LOOKBACK_ROWS: int = 24
    OPTIMIZATION_CPU_HIGH_THRESHOLD: float = 85.0
    OPTIMIZATION_CPU_LOW_THRESHOLD: float = 15.0
    OPTIMIZATION_MEMORY_HIGH_THRESHOLD: float = 85.0
    OPTIMIZATION_MEMORY_LOW_THRESHOLD: float = 15.0
    OPTIMIZATION_TARGET_CPU_PERCENT: float = 60.0
    OPTIMIZATION_TARGET_CPU_BAND: float = 15.0
    OPTIMIZATION_MAX_SCALE_REPLICAS: int = 10
    OPTIMIZATION_COST_RIGHTSIZING_SAVINGS_FRACTION: float = 0.15
    # A dismissed/applied recommendation of a given type won't be recreated
    # for this many minutes even if its condition still holds, so a
    # deployment hovering right at a threshold doesn't get the exact same
    # recommendation re-created on every evaluation run right after a user
    # dismissed it.
    OPTIMIZATION_RECOMMENDATION_COOLDOWN_MINUTES: int = 60
    # Below this confidence, a stale/uncertain LSTM forecast is ignored and
    # the recommendation engine falls back to past actuals only - see
    # OptimizationService._effective_cpu/_effective_memory.
    OPTIMIZATION_PREDICTION_CONFIDENCE_THRESHOLD: float = 0.5
    # HPA-style target for memory, mirroring OPTIMIZATION_TARGET_CPU_PERCENT -
    # used to compute a concrete target_memory_limit_mb for increase_memory/
    # reduce_memory recommendations (see recommendation_engine.evaluate()).
    OPTIMIZATION_TARGET_MEMORY_PERCENT: float = 70.0

    # Auto-apply (off by default - a recommendation with a real, bounded
    # numeric target can apply itself immediately instead of waiting for an
    # operator/admin to action it via PATCH /optimization-recommendations/{id}.
    # Only recommendation types that carry a concrete, already safety-bounded
    # target value (see RecommendationCondition.target_replicas/
    # target_memory_limit_mb) are ever eligible - "increase_cpu"/"reduce_cpu"
    # (no CPU-limit field exists on Deployment to act on) and "optimize_cost"
    # (a financial suggestion, not an infrastructure change) never auto-apply
    # regardless of this setting, since there is nothing concrete to apply.
    OPTIMIZATION_AUTO_APPLY_ENABLED: bool = False
    OPTIMIZATION_AUTO_APPLY_TYPES: str = "scale_deployment,increase_memory,reduce_memory"

    # Real-time cloud metrics sync (Phase 12) - periodically pulls real
    # telemetry from each linked deployment's cloud provider account
    CLOUD_SYNC_INTERVAL_MINUTES: int = 15
    CLOUD_SYNC_LOOKBACK_MINUTES: int = 15

    # Real AWS Cost Explorer billing sync (Phase 18) - how many complete
    # past calendar months of spend to pull per sync.
    CLOUD_COST_SYNC_LOOKBACK_MONTHS: int = 3

    # Structured logging + distributed tracing (Phase 19). Logs are always
    # emitted as one JSON object per line (see app/utils/logger.py) - there
    # is no plain-text fallback, since the point is machine-parseable
    # output a real log aggregator (ELK/Loki/CloudWatch Logs Insights)
    # can query on fields, not just grep.
    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "cloud-ai-platform-backend"
    # Empty (default): spans export to stdout via ConsoleSpanExporter, so
    # tracing is genuinely observable (`docker compose logs backend`) with
    # zero external services required. Set this to a real collector's URL
    # (e.g. an OTel Collector, Jaeger, Tempo, Grafana Cloud) to switch to a
    # real OTLP/HTTP export instead - the same env var name the
    # OpenTelemetry SDK itself conventionally reads.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def optimization_auto_apply_types_set(self) -> set[str]:
        return {t.strip() for t in self.OPTIMIZATION_AUTO_APPLY_TYPES.split(",") if t.strip()}

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so the environment is parsed only once."""
    return Settings()
