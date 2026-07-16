"""Database access for the ML pipeline.

The pipeline is an independent project (its own requirements/Docker image),
so rather than importing the backend's SQLAlchemy ORM models directly (which
would couple two separately-deployable services), it reflects the tables it
needs straight off the live MySQL schema. This means the pipeline always
matches whatever migration state the database is actually in, with zero
duplicated column definitions to keep in sync by hand.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.engine import Engine

load_dotenv()

_TABLE_NAMES = [
    "deployments",
    "pods",
    "resource_usage",
    "metrics",
    "predictions",
    "anomaly_detections",
    "failure_predictions",
]


def get_engine() -> Engine:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "cloudai")
    password = os.getenv("MYSQL_PASSWORD", "cloudai_password")
    database = os.getenv("MYSQL_DATABASE", "cloud_ai_platform")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)


def reflect_tables(engine: Engine) -> dict[str, Table]:
    metadata = MetaData()
    metadata.reflect(bind=engine, only=_TABLE_NAMES)
    return {name: metadata.tables[name] for name in _TABLE_NAMES}
