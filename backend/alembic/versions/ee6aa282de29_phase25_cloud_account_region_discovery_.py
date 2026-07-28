"""phase25_cloud_account_region_discovery_fields

Revision ID: ee6aa282de29
Revises: 734043a1ade2
Create Date: 2026-07-28 20:16:35.842213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee6aa282de29'
down_revision: Union[str, None] = '734043a1ade2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL rejects a literal DEFAULT on a TEXT column (error 1101), so
    # available_regions is backfilled the standard 3-step way instead of a
    # server_default: add nullable, backfill every existing (pre-Phase-25)
    # account with an empty list, then tighten to NOT NULL. connection_status
    # is a plain VARCHAR, so its server_default works directly - same
    # backfill intent as email_verified's Phase 24 migration, just split
    # across two techniques because of the column type difference.
    op.add_column('cloud_provider_accounts', sa.Column('available_regions', sa.Text(), nullable=True))
    op.execute("UPDATE cloud_provider_accounts SET available_regions = '[]' WHERE available_regions IS NULL")
    op.alter_column('cloud_provider_accounts', 'available_regions', existing_type=sa.Text(), nullable=False)

    op.add_column('cloud_provider_accounts', sa.Column('last_region_sync', sa.DateTime(), nullable=True))
    op.add_column(
        'cloud_provider_accounts',
        sa.Column('connection_status', sa.String(length=30), nullable=False, server_default=sa.text("'CONNECTED'")),
    )


def downgrade() -> None:
    op.drop_column('cloud_provider_accounts', 'connection_status')
    op.drop_column('cloud_provider_accounts', 'last_region_sync')
    op.drop_column('cloud_provider_accounts', 'available_regions')
