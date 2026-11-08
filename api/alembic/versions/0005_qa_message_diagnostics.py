"""qa_message.diagnostics

Stores what happened during a Q&A turn so the eval page can show it: which
action the agent took, the searches it ran, the passages retrieval returned with
their distances, the citations emitted, and any stream error.

Nullable, so every existing row stays valid and the page can say "no
diagnostics" for older turns rather than pretending it was a clean one.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "qa_message",
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("qa_message", "diagnostics")
