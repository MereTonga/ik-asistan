"""document_chunks.embedding icin HNSW indeksi; company_id ve thread_id icin btree indeksler

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_documents_company_id', 'documents', ['company_id'])
    op.create_index('ix_document_chunks_company_id', 'document_chunks', ['company_id'])
    op.create_index('ix_email_threads_company_id', 'email_threads', ['company_id'])
    op.create_index('ix_messages_thread_id', 'messages', ['thread_id'])
    # pgvector HNSW: kosinus mesafesi icin yaklasik en-yakin-komsu indeksi (retrieval.py cosine_distance kullanir)
    op.create_index(
        'ix_document_chunks_embedding',
        'document_chunks',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_document_chunks_embedding', table_name='document_chunks')
    op.drop_index('ix_messages_thread_id', table_name='messages')
    op.drop_index('ix_email_threads_company_id', table_name='email_threads')
    op.drop_index('ix_document_chunks_company_id', table_name='document_chunks')
    op.drop_index('ix_documents_company_id', table_name='documents')
