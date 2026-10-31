"""composite index for coverage lookups

Coverage reads filter ``WHERE user_id = ? AND book_id = ?`` and aggregate by
section. The existing single-column indexes on coverage_event force a
bitmap-and; a composite index on (user_id, book_id, section_id) with
event_type included answers the whole read from one index scan.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_coverage_event_user_book_section",
        "coverage_event",
        ["user_id", "book_id", "section_id"],
        postgresql_include=["event_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coverage_event_user_book_section",
        table_name="coverage_event",
    )
