"""created_at kolonlari timestamptz, unique kisitlar isimlendirildi, messages.confidence_score Float + is_grounded

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-27 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tum created_at kolonlari naive 'timestamp' idi; degerler uygulama tarafindan UTC yazildi.
TABLES_WITH_CREATED_AT = ("companies", "documents", "document_chunks", "email_threads", "messages")

# Postgres'in otomatik verdigi kisit adlari -> modeldeki naming_convention'a uyan adlar
CONSTRAINT_RENAMES = (
    ("messages", "messages_message_id_header_key", "uq_messages_message_id_header"),
    ("companies", "companies_email_domain_key", "uq_companies_email_domain"),
    ("email_threads", "email_threads_root_message_id_header_key", "uq_email_threads_root_message_id_header"),
)


def _constraint_exists(name: str) -> bool:
    return bool(op.get_bind().execute(sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name}).scalar())


def _rename_constraint_if_exists(table: str, old_name: str, new_name: str) -> None:
    # Sifirdan kurulan veritabanlarinda (CI, down -v) kisitlar naming_convention sayesinde zaten yeni adla
    # olusur; yalnizca eski Postgres varsayilan adiyla duran kisitlar yeniden adlandirilir.
    if _constraint_exists(old_name) and not _constraint_exists(new_name):
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old_name} TO {new_name}")


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES_WITH_CREATED_AT:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
            f"USING created_at AT TIME ZONE 'UTC'"
        )

    # confidence_score hic yazilmamisti (hep NULL); artik en yuksek benzerlik skoru (float) tutulacak
    op.execute(
        "ALTER TABLE messages ALTER COLUMN confidence_score TYPE DOUBLE PRECISION "
        "USING NULLIF(confidence_score, '')::double precision"
    )
    op.add_column('messages', sa.Column('is_grounded', sa.Boolean(), nullable=True))

    for table, old_name, new_name in CONSTRAINT_RENAMES:
        _rename_constraint_if_exists(table, old_name, new_name)


def downgrade() -> None:
    """Downgrade schema."""
    for table, old_name, new_name in CONSTRAINT_RENAMES:
        _rename_constraint_if_exists(table, new_name, old_name)

    op.drop_column('messages', 'is_grounded')
    op.execute("ALTER TABLE messages ALTER COLUMN confidence_score TYPE VARCHAR USING confidence_score::text")

    for table in TABLES_WITH_CREATED_AT:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
            f"USING created_at AT TIME ZONE 'UTC'"
        )
