"""Ajout completed_at à ChangeRequest

Revision ID: 5601fffa89d0
Revises: a389f1db2ed7
Create Date: 2025-04-05 03:56:39.071298

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5601fffa89d0'
down_revision = 'a389f1db2ed7'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('change_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('requested_at',
               existing_type=sa.DATETIME(),
               nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('change_requests', schema=None) as batch_op:
        batch_op.alter_column('requested_at',
               existing_type=sa.DATETIME(),
               nullable=True)
        batch_op.drop_column('completed_at')

    # ### end Alembic commands ###
