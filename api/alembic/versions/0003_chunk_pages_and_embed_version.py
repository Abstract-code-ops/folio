"""chunk page ranges and embed version

Adds the columns the parser and chunker work (U4/U5) needs in order to
persist what it already computes:

- ``chunk.page_start`` / ``chunk.page_end``: nullable integers. Rows ingested
  before parser v2 keep NULL until the book is re-ingested, so this is
  additive and safe on the existing corpus.
- ``section.embed_version`` / ``chunk.embed_version``: smallint, NOT NULL,
  server default 1. Existing rows are stamped 1 by the server default, which is
  correct: their embeddings were produced without the nomic task prefixes. U7
  writes 2 for the prefix-based inputs, so a re-embed can be partial and
  resumable.

Deliberately untouched: ``section.parent_section_id`` (already exists) and the
``vector(768)`` dimension.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17 10:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunk", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("chunk", sa.Column("page_end", sa.Integer(), nullable=True))
    op.add_column(
        "section",
        sa.Column(
            "embed_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "chunk",
        sa.Column(
            "embed_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chunk", "embed_version")
    op.drop_column("section", "embed_version")
    op.drop_column("chunk", "page_end")
    op.drop_column("chunk", "page_start")
