"""Alembic environment configuration.

The database URL and target metadata come from the application's own
settings/models modules so migrations always stay in sync with the
SQLAlchemy ORM models in `app.models`, instead of duplicating connection
config in alembic.ini.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.settings import get_settings
from app.database.base import Base

import app.models  # noqa: F401  (registers all models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Restrict include_schemas=True to exactly our two application
    databases - without this, MySQL's autogenerate tries to reflect every
    schema the server has (mysql, sys, performance_schema, the *_test
    databases, ...), including ones the app's MySQL user has no read access
    to at all, which fails outright rather than just producing noise."""
    if type_ == "schema":
        return name in (None, settings.MYSQL_DATABASE, settings.AUTH_MYSQL_DATABASE)
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # Users/roles/user_roles live in a separate database on the same
        # MySQL server (AUTH_MYSQL_DATABASE - see docs/PHASE_13.md); without
        # this, autogenerate only reflects the connection's default schema
        # and would think those tables (and every cross-schema FK) don't exist.
        include_schemas=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
