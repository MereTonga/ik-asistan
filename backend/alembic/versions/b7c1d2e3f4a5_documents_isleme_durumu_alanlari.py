"""documents tablosuna document_quality ve error_message eklendi; takili belgeler failed yapildi

Revision ID: b7c1d2e3f4a5
Revises: 4814a48ff280
Create Date: 2026-10-27 03:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = '4814a48ff280'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('document_quality', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('error_message', sa.Text(), nullable=True))

    # Faz 13 oncesi: isleme sirasinda patlayan belgeler metinsiz olarak 'pending_approval'da
    # takili kaliyordu. Bunlari 'failed' olarak isaretle ki panelde gorunur ve yeniden islenebilir olsun.
    op.execute(
        "UPDATE documents SET status = 'failed', "
        "error_message = 'Isleme tamamlanmamis (Faz 13 oncesi kayit); yeniden isleyin.' "
        "WHERE status = 'pending_approval' AND (raw_extracted_text IS NULL OR raw_extracted_text = '')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Yeni durumlar eski kodda bilinmiyor; en yakin eski duruma cevir.
    op.execute("UPDATE documents SET status = 'pending_approval' WHERE status IN ('processing', 'failed', 'indexing')")
    op.drop_column('documents', 'error_message')
    op.drop_column('documents', 'document_quality')
