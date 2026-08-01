"""phase29_cloud_resource_discovery_tables

Revision ID: b527c59febd3
Revises: 7d2e8fc521a2
Create Date: 2026-08-01 12:44:36.273048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b527c59febd3'
down_revision: Union[str, None] = '7d2e8fc521a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('cloud_resources',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('cloud_provider_account_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('resource_type', sa.String(length=50), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('region', sa.String(length=50), nullable=False),
    sa.Column('availability_zone', sa.String(length=30), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('instance_type', sa.String(length=50), nullable=True),
    sa.Column('public_ip', sa.String(length=45), nullable=True),
    sa.Column('private_ip', sa.String(length=45), nullable=True),
    sa.Column('tags_json', sa.Text(), nullable=True),
    sa.Column('extra_json', sa.Text(), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cloud_provider_account_id'], ['cloud_provider_accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['cloud_ai_auth.users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cloud_provider_account_id', 'resource_type', 'region', 'external_id', name='uq_cloud_resource_identity')
    )
    op.create_index('ix_cloud_resources_account_type', 'cloud_resources', ['cloud_provider_account_id', 'resource_type'], unique=False)
    op.create_index(op.f('ix_cloud_resources_cloud_provider_account_id'), 'cloud_resources', ['cloud_provider_account_id'], unique=False)
    op.create_index(op.f('ix_cloud_resources_provider'), 'cloud_resources', ['provider'], unique=False)
    op.create_index(op.f('ix_cloud_resources_resource_type'), 'cloud_resources', ['resource_type'], unique=False)
    op.create_index(op.f('ix_cloud_resources_user_id'), 'cloud_resources', ['user_id'], unique=False)
    op.create_table('cloud_resource_metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cloud_resource_id', sa.Integer(), nullable=False),
    sa.Column('cpu_usage_percent', sa.Float(), nullable=False),
    sa.Column('network_in_kbps', sa.Float(), nullable=False),
    sa.Column('network_out_kbps', sa.Float(), nullable=False),
    sa.Column('disk_read_bytes', sa.Float(), nullable=False),
    sa.Column('disk_write_bytes', sa.Float(), nullable=False),
    sa.Column('status_check_failed', sa.Integer(), nullable=True),
    sa.Column('memory_usage_mb', sa.Float(), nullable=True),
    sa.Column('recorded_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cloud_resource_id'], ['cloud_resources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cloud_resource_metrics_cloud_resource_id'), 'cloud_resource_metrics', ['cloud_resource_id'], unique=False)
    op.create_index('ix_cloud_resource_metrics_resource_time', 'cloud_resource_metrics', ['cloud_resource_id', 'recorded_at'], unique=False)
    op.add_column('cloud_provider_accounts', sa.Column('last_discovery_at', sa.DateTime(), nullable=True))
    op.add_column('cloud_provider_accounts', sa.Column('last_discovery_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('cloud_provider_accounts', 'last_discovery_error')
    op.drop_column('cloud_provider_accounts', 'last_discovery_at')
    op.drop_index('ix_cloud_resource_metrics_resource_time', table_name='cloud_resource_metrics')
    op.drop_index(op.f('ix_cloud_resource_metrics_cloud_resource_id'), table_name='cloud_resource_metrics')
    op.drop_table('cloud_resource_metrics')
    op.drop_index(op.f('ix_cloud_resources_user_id'), table_name='cloud_resources')
    op.drop_index(op.f('ix_cloud_resources_resource_type'), table_name='cloud_resources')
    op.drop_index(op.f('ix_cloud_resources_provider'), table_name='cloud_resources')
    op.drop_index(op.f('ix_cloud_resources_cloud_provider_account_id'), table_name='cloud_resources')
    op.drop_index('ix_cloud_resources_account_type', table_name='cloud_resources')
    op.drop_table('cloud_resources')
