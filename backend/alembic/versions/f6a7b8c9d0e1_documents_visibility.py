"""documents tablosuna visibility (internal | public) eklendi

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Mevcut tum belgeler 'internal' kalir: guvenli taraf, IK acikca degistirmedikce disariya cevap kaynagi olmazlar
    op.add_column('documents', sa.Column('visibility', sa.String(), nullable=False, server_default='internal'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'visibility')
