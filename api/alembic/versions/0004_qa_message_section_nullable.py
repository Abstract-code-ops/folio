"""qa_message.section_id becomes nullable

Book-scoped Q&A no longer always touches a section. With the U11 agent in front
of retrieval, a greeting or an off-topic message is answered without retrieving
anything, so there is no section to point at. Writing a bogus section id was the
only alternative, and it would have polluted coverage accounting.

Downgrade will fail if any NULL rows exist; delete or re-scope those first.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "qa_message",
        "section_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "qa_message",
        "section_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
