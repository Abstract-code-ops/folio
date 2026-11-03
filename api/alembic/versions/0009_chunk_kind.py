"""chunk kind (text vs table)

Adds ``chunk.kind`` so a chunk can be flagged as a Markdown table. Table
chunks are embedded with a structure hint and rendered as structured data in
the Q&A context, instead of being flattened into prose.

Additive and safe on the existing corpus: the column is NOT NULL with a server
default of ``'text'``, so every existing row is backfilled to ``'text'``.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunk",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'text'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chunk", "kind")
