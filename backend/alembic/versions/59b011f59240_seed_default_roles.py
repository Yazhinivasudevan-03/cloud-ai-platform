"""seed default roles

Data-only migration (no schema change): ensures the three platform roles
that Phase 2's RBAC policy depends on (viewer/operator/admin) exist, so
`POST /users/{id}/roles` can reference them by name without an admin ever
needing to invent role rows by hand. Idempotent - safe to run against a
database that already has some of these roles (e.g. `viewer`, which is
also lazily created by AuthService.register on first use).

Revision ID: 59b011f59240
Revises: f5a5b68878ec
Create Date: 2026-07-15 15:24:26.983334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '59b011f59240'
down_revision: Union[str, None] = 'f5a5b68878ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES_TABLE = sa.table(
    "roles",
    sa.column("name", sa.String),
    sa.column("description", sa.String),
)

_SEED_ROLES = [
    {"name": "viewer", "description": "Read-only access to dashboards and reports"},
    {"name": "operator", "description": "Can create and update platform resources"},
    {
        "name": "admin",
        "description": "Full administrative access, including user and role management",
    },
]


def upgrade() -> None:
    connection = op.get_bind()
    existing_names = set(
        connection.execute(sa.text("SELECT name FROM roles")).scalars().all()
    )
    to_insert = [row for row in _SEED_ROLES if row["name"] not in existing_names]
    if to_insert:
        op.bulk_insert(_ROLES_TABLE, to_insert)


def downgrade() -> None:
    seed_names = [row["name"] for row in _SEED_ROLES]
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM roles WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True)
        ),
        {"names": seed_names},
    )
