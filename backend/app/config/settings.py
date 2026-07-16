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

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "5/minute"

    # Alerting
    ALERT_EVALUATION_INTERVAL_MINUTES: int = 5
    ALERT_CPU_WARNING_THRESHOLD: float = 60.0
    ALERT_CPU_CRITICAL_THRESHOLD: float = 80.0
    ALERT_CPU_SATURATED_THRESHOLD: float = 100.0
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

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
