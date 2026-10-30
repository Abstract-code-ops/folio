"""drop note_link chunk_id and distance

The local-first sync writes links with a section id, heading path, page range and
excerpt hash only. ``chunk_id`` and ``distance`` are no longer produced -- the
batch upsert leaves them unset and nothing reads them -- so they are dropped.
``excerpt_hash`` stays: it is still derived server-side on every link write.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dropping the column also drops its index and the chunk foreign key.
    op.drop_column("note_link", "chunk_id")
    op.drop_column("note_link", "distance")


def downgrade() -> None:
    op.add_column(
        "note_link",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("note_link", sa.Column("distance", sa.Float(), nullable=True))
