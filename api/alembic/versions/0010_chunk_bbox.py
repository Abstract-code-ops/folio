"""chunk bbox (figure region)

Adds ``chunk.bbox`` so a figure chunk can record where the diagram sits on the
page (``{x0,y0,x1,y1}`` in PDF points). Only ``kind='figure'`` rows set it;
everything else stays NULL. The caption lives in ``chunk.content`` — no image
is stored.

Additive and safe on the existing corpus.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunk",
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunk", "bbox")
