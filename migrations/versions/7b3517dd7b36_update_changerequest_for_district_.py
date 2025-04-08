"""Update ChangeRequest for district reassignment workflow

Revision ID: 7b3517dd7b36
Revises: 
Create Date: 2025-04-08 11:50:20.634696

"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7b3517dd7b36'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Supprimer l'ancienne table
    op.drop_table('change_requests')

    # Créer la nouvelle table avec la structure mise à jour
    op.create_table(
        'change_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('target_district_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending_data_entry'),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('data_entry_responded_at', sa.DateTime(), nullable=True),
        sa.Column('team_lead_responded_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['requester_id'], ['users.id'], name='fk_change_requests_requester_id'),
        sa.ForeignKeyConstraint(['target_district_id'], ['locations.id'], name='fk_change_requests_target_district_id'),
        sa.CheckConstraint(
            "status IN ('pending_data_entry', 'pending_team_lead', 'accepted', 'rejected')",
            name='check_change_request_status'
        ),
        sa.CheckConstraint(
            "data_entry_responded_at IS NULL OR data_entry_responded_at >= requested_at",
            name='check_data_entry_response_timing'
        ),
        sa.CheckConstraint(
            "team_lead_responded_at IS NULL OR team_lead_responded_at >= data_entry_responded_at",
            name='check_team_lead_response_timing'
        ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    # Supprimer la nouvelle table
    op.drop_table('change_requests')

    # Recréer l'ancienne table
    op.create_table(
        'change_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('new_region_id', sa.Integer(), nullable=False),
        sa.Column('new_district_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('current_data_entry_id', sa.Integer(), nullable=True),
        sa.Column('team_lead_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_change_requests_user_id'),
        sa.ForeignKeyConstraint(['new_region_id'], ['locations.id'], name='fk_change_requests_new_region_id'),
        sa.ForeignKeyConstraint(['new_district_id'], ['locations.id'], name='fk_change_requests_new_district_id'),
        sa.ForeignKeyConstraint(['current_data_entry_id'], ['users.id'], name='fk_change_requests_current_data_entry_id'),
        sa.ForeignKeyConstraint(['team_lead_id'], ['users.id'], name='fk_change_requests_team_lead_id'),
        sa.CheckConstraint(
            "status IN ('pending_data_entry', 'pending_team_lead', 'accepted', 'rejected')",
            name='check_change_request_status'
        ),
        sa.CheckConstraint(
            "responded_at IS NULL OR responded_at >= requested_at",
            name='check_response_timing'
        ),
        sa.CheckConstraint(
            "(status IN ('pending_data_entry') AND current_data_entry_id IS NOT NULL) OR "
            "(status IN ('pending_team_lead') AND team_lead_id IS NOT NULL) OR "
            "(status IN ('accepted', 'rejected'))",
            name='check_validator_assignment'
        ),
        sa.PrimaryKeyConstraint('id')
    )