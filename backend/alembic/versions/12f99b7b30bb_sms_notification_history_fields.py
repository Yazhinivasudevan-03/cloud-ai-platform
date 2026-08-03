"""sms_notification_history_fields

Revision ID: 12f99b7b30bb
Revises: b527c59febd3
Create Date: 2026-08-01 14:42:46.590687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12f99b7b30bb'
down_revision: Union[str, None] = 'b527c59febd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('cloud_provider_account_id', sa.Integer(), nullable=True))
    op.add_column('notifications', sa.Column('phone_number', sa.String(length=20), nullable=True))
    op.add_column('notifications', sa.Column('message_sid', sa.String(length=64), nullable=True))
    op.add_column('notifications', sa.Column('delivery_status', sa.Text(), nullable=True))
    op.create_index(op.f('ix_notifications_cloud_provider_account_id'), 'notifications', ['cloud_provider_account_id'], unique=False)
    op.create_foreign_key(None, 'notifications', 'cloud_provider_accounts', ['cloud_provider_account_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(None, 'notifications', type_='foreignkey')
    op.drop_index(op.f('ix_notifications_cloud_provider_account_id'), table_name='notifications')
    op.drop_column('notifications', 'delivery_status')
    op.drop_column('notifications', 'message_sid')
    op.drop_column('notifications', 'phone_number')
    op.drop_column('notifications', 'cloud_provider_account_id')
