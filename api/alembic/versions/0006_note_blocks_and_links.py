"""note_block and note_link

Adds the note document: an ordered list of blocks, and links that attach a block
to a place in the book.

Purely additive -- no existing table or column is touched, so the application
keeps running unchanged until this is applied. Nothing queries the new tables
yet.

The two foreign keys to ``chunk`` and ``section`` are ``ON DELETE SET NULL`` on
purpose. Re-ingestion deletes a section's chunks and recreates them
(``workers/ingest.py``), and a citation must survive that by falling back to its
stored anchor -- heading path, page range and excerpt hash -- rather than
disappearing or blocking the job.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "note_block",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("note_session.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="0-based position of this block within its note",
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "heading", "paragraph", "bullet", "card",
                name="note_block_kind", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "origin",
            postgresql.ENUM(
                "typed", "ai", "ocr",
                name="note_block_origin", create_type=True,
            ),
            nullable=False,
            server_default="typed",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=False),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )

    op.create_table(
        "note_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "block_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("note_block.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunk.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("section.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("anchor_heading_path", sa.String(512), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_hash", sa.String(64), nullable=False),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column(
            "origin",
            postgresql.ENUM(
                "generated", "auto", "manual",
                name="note_link_origin", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "suggested", "accepted", "dismissed",
                name="note_link_status", create_type=True,
            ),
            nullable=False,
            server_default="accepted",
            index=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=False),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("note_link")
    op.drop_table("note_block")

    # Drop enums (CASCADE required if any column still references them)
    op.execute("DROP TYPE IF EXISTS note_link_status CASCADE")
    op.execute("DROP TYPE IF EXISTS note_link_origin CASCADE")
    op.execute("DROP TYPE IF EXISTS note_block_origin CASCADE")
    op.execute("DROP TYPE IF EXISTS note_block_kind CASCADE")
