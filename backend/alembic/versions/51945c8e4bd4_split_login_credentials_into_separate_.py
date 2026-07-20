"""split login credentials into separate auth database

Revision ID: 51945c8e4bd4
Revises: 093355726a4c
Create Date: 2026-07-20 05:31:55.305466

Moves users/roles/user_roles out of the main application database into a
dedicated AUTH_MYSQL_DATABASE (default "cloud_ai_auth") on the same MySQL
server, isolating login credentials from all other application data (see
docs/PHASE_13.md). Uses RENAME TABLE (instant, no data copy/loss risk)
rather than create+copy+drop. The six tables that reference users.id
(api_keys, audit_logs, cloud_provider_accounts, notifications, projects,
settings) and user_roles itself have their foreign keys dropped and
recreated pointing across the database boundary, since MySQL requires an
explicit schema-qualified foreign key for a cross-database reference and
won't let a referenced table be renamed out from under an existing
constraint.
"""
from typing import Sequence, Union

from alembic import op

from app.config.settings import get_settings

# revision identifiers, used by Alembic.
revision: str = '51945c8e4bd4'
down_revision: Union[str, None] = '093355726a4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTH_SCHEMA = get_settings().AUTH_MYSQL_DATABASE

# (constraint_name, table, local_column, referent_table, referent_column, ondelete)
_USER_FKS = [
    ("api_keys_ibfk_1", "api_keys", "user_id", "users", "id", "CASCADE"),
    ("audit_logs_ibfk_1", "audit_logs", "user_id", "users", "id", "SET NULL"),
    ("cloud_provider_accounts_ibfk_1", "cloud_provider_accounts", "user_id", "users", "id", "CASCADE"),
    ("notifications_ibfk_2", "notifications", "user_id", "users", "id", "CASCADE"),
    ("projects_ibfk_1", "projects", "owner_id", "users", "id", "CASCADE"),
    ("settings_ibfk_1", "settings", "user_id", "users", "id", "CASCADE"),
]
_USER_ROLES_FKS = [
    ("user_roles_ibfk_2", "user_id", "users", "id", "CASCADE"),
    ("user_roles_ibfk_1", "role_id", "roles", "id", "CASCADE"),
]


def upgrade() -> None:
    op.execute(
        f"CREATE DATABASE IF NOT EXISTS `{AUTH_SCHEMA}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )

    for constraint_name, table, *_ in _USER_FKS:
        op.drop_constraint(constraint_name, table, type_="foreignkey")
    for constraint_name, *_ in _USER_ROLES_FKS:
        op.drop_constraint(constraint_name, "user_roles", type_="foreignkey")

    op.execute(f"RENAME TABLE users TO `{AUTH_SCHEMA}`.users")
    op.execute(f"RENAME TABLE roles TO `{AUTH_SCHEMA}`.roles")
    op.execute(f"RENAME TABLE user_roles TO `{AUTH_SCHEMA}`.user_roles")

    for constraint_name, table, local_col, referent_table, referent_col, ondelete in _USER_FKS:
        op.create_foreign_key(
            constraint_name, table, referent_table, [local_col], [referent_col],
            referent_schema=AUTH_SCHEMA, ondelete=ondelete,
        )
    for constraint_name, local_col, referent_table, referent_col, ondelete in _USER_ROLES_FKS:
        op.create_foreign_key(
            constraint_name, "user_roles", referent_table, [local_col], [referent_col],
            source_schema=AUTH_SCHEMA, referent_schema=AUTH_SCHEMA, ondelete=ondelete,
        )

    # SQLAlchemy's auto-generated name for an unnamed index changes once its
    # table has a schema (roles.name's index=True index goes from
    # ix_roles_name to ix_<schema>_roles_name) - rename in place so a future
    # `alembic revision --autogenerate` sees no diff against the ORM models.
    op.execute(f"ALTER TABLE `{AUTH_SCHEMA}`.roles RENAME INDEX ix_roles_name TO ix_{AUTH_SCHEMA}_roles_name")


def downgrade() -> None:
    op.execute(f"ALTER TABLE `{AUTH_SCHEMA}`.roles RENAME INDEX ix_{AUTH_SCHEMA}_roles_name TO ix_roles_name")

    for constraint_name, *_ in _USER_ROLES_FKS:
        op.drop_constraint(constraint_name, "user_roles", type_="foreignkey", schema=AUTH_SCHEMA)
    for constraint_name, table, *_ in _USER_FKS:
        op.drop_constraint(constraint_name, table, type_="foreignkey")

    op.execute(f"RENAME TABLE `{AUTH_SCHEMA}`.users TO users")
    op.execute(f"RENAME TABLE `{AUTH_SCHEMA}`.roles TO roles")
    op.execute(f"RENAME TABLE `{AUTH_SCHEMA}`.user_roles TO user_roles")

    for constraint_name, table, local_col, referent_table, referent_col, ondelete in _USER_FKS:
        op.create_foreign_key(
            constraint_name, table, referent_table, [local_col], [referent_col], ondelete=ondelete,
        )
    for constraint_name, local_col, referent_table, referent_col, ondelete in _USER_ROLES_FKS:
        op.create_foreign_key(
            constraint_name, "user_roles", referent_table, [local_col], [referent_col], ondelete=ondelete,
        )

    op.execute(f"DROP DATABASE IF EXISTS `{AUTH_SCHEMA}`")
