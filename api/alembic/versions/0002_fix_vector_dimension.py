"""fix_vector_dimension

Alter section.embedding and chunk.embedding from vector(1536) to
vector(768) to match the switch from text-embedding-ada-002 (1536-dim)
to nomic-embed-text (768-dim) via Ollama.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-15 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import pgvector  # noqa: F401 — registers Vector type with SQLAlchemy

# revision identifiers
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter section embedding column from vector(1536) to vector(768)
    op.execute(
        "ALTER TABLE section ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )
    # Alter chunk embedding column from vector(1536) to vector(768)
    op.execute(
        "ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )


def downgrade() -> None:
    # Revert section embedding column back to vector(1536)
    op.execute(
        "ALTER TABLE section ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    # Revert chunk embedding column back to vector(1536)
    op.execute(
        "ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
