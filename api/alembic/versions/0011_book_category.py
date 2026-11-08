"""book category

Adds ``book.category`` for the library's category filter. Nullable — existing
books stay uncategorised until edited. Indexed because the library filters by
it.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("book", sa.Column("category", sa.String(length=64), nullable=True))
    op.create_index("ix_book_category", "book", ["category"])


def downgrade() -> None:
    op.drop_index("ix_book_category", table_name="book")
    op.drop_column("book", "category")
