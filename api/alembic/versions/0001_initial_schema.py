"""initial_schema

Create all six core tables: book, section, chunk, note_session,
coverage_event, qa_message. Also enable the pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2025-01-15 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy  # noqa: F401 — registers the Vector type; the bare
# `import pgvector` does not load the sqlalchemy submodule, so a from-scratch
# upgrade died on pgvector.sqlalchemy.Vector below.
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pgvector extension ─────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Book ───────────────────────────────────────────────────
    op.create_table(
        "book",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False, index=True),
        sa.Column("author", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_url", sa.String(1024), nullable=True),
        sa.Column("storage_url", sa.String(1024), nullable=False),
        sa.Column(
            "ingestion_status",
            postgresql.ENUM(
                "not_started",
                "processing",
                "completed",
                "failed",
                name="ingestion_status",
                create_type=True,
            ),
            nullable=False,
            server_default="not_started",
            index=True,
        ),
        sa.Column("section_count", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )

    # ── Section ────────────────────────────────────────────────
    op.create_table(
        "section",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "book_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("book.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "parent_section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("section.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("chapter_index", sa.Integer(), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heading", sa.String(512), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_connective",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("section_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1536),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )

    # ── Chunk ──────────────────────────────────────────────────
    op.create_table(
        "chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("section.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1536),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )

    # ── NoteSession ────────────────────────────────────────────
    op.create_table(
        "note_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column(
            "book_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(
                "pasted", "ai_generated", name="note_source", create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("matched_section_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "processing", "completed", "failed",
                name="note_session_status", create_type=True,
            ),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )

    # ── CoverageEvent ──────────────────────────────────────────
    op.create_table(
        "coverage_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column(
            "book_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column(
            "section_id", postgresql.UUID(as_uuid=True),
            nullable=False, index=True,
        ),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "page_viewed", "note_matched", "notes_generated",
                "qa_asked", "quiz_answered",
                name="event_type", create_type=True,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("event_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False),
            server_default=sa.func.now(), nullable=False, index=True,
        ),
    )

    # ── QAMessage ──────────────────────────────────────────────
    op.create_table(
        "qa_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column(
            "book_id", postgresql.UUID(as_uuid=True), nullable=False, index=True,
        ),
        sa.Column(
            "section_id", postgresql.UUID(as_uuid=True),
            nullable=False, index=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("qa_message")
    op.drop_table("coverage_event")
    op.drop_table("note_session")
    op.drop_table("chunk")
    op.drop_table("section")
    op.drop_table("book")

    # Drop enums (CASCADE required if any column still references them)
    op.execute("DROP TYPE IF EXISTS event_type CASCADE")
    op.execute("DROP TYPE IF EXISTS note_source CASCADE")
    op.execute("DROP TYPE IF EXISTS note_session_status CASCADE")
    op.execute("DROP TYPE IF EXISTS ingestion_status CASCADE")
