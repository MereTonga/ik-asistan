"""authorized_senders tablosu; email_threads.is_external

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-27 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'authorized_senders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name='fk_authorized_senders_company_id_companies'),
        sa.PrimaryKeyConstraint('id', name='pk_authorized_senders'),
        sa.UniqueConstraint('email', name='uq_authorized_senders_email'),
    )
    op.create_index('ix_authorized_senders_company_id', 'authorized_senders', ['company_id'])
    # Dis gonderen isareti: mevcut tum thread'ler calisanlara ait (false)
    op.add_column('email_threads', sa.Column('is_external', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('email_threads', 'is_external')
    op.drop_index('ix_authorized_senders_company_id', table_name='authorized_senders')
    op.drop_table('authorized_senders')
