"""Initial state from Render database

Revision ID: 683aa24e85e1
Revises: 
Create Date: 2025-04-11 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '683aa24e85e1'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Migration vide : l'état de la base de données est déjà synchronisé avec Render
    pass

def downgrade():
    # Migration vide : pas de rétrogradation possible sans l'historique complet
    pass