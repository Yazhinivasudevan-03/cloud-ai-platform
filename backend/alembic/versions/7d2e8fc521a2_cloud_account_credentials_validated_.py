"""cloud_account_credentials_validated_fields

Revision ID: 7d2e8fc521a2
Revises: ee6aa282de29
Create Date: 2026-07-29 22:49:09.858000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d2e8fc521a2'
down_revision: Union[str, None] = 'ee6aa282de29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfills every pre-existing account as already-validated (server_default
    # '1') - preserving today's implicit assumption that an already-connected
    # account's credentials work, the same backfill-safe pattern as Phase 24's
    # email_verified migration. A brand-new account created after this
    # migration gets credentials_validated=False at the ORM level (see
    # CloudProviderAccount.credentials_validated's Python-side default) -
    # only a real, successful POST /{id}/validate-credentials call flips it.
    op.add_column(
        'cloud_provider_accounts',
        sa.Column('credentials_validated', sa.Boolean(), nullable=False, server_default=sa.text('1')),
    )
    op.add_column('cloud_provider_accounts', sa.Column('credentials_validated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('cloud_provider_accounts', 'credentials_validated_at')
    op.drop_column('cloud_provider_accounts', 'credentials_validated')
