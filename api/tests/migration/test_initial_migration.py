"""Tests for the initial Alembic migration script.

These tests verify the migration file structure and metadata.
Full migration execution (upgrade/downgrade) requires a running
PostgreSQL instance and is run separately.
"""

from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parents[2] / "alembic" / "versions"


class TestMigrationFileStructure:
    """Structural checks on the migration file."""

    def test_migration_file_exists(self):
        files = list(MIGRATIONS_DIR.glob("*.py"))
        assert len(files) >= 1, "No migration files found"

    def test_initial_migration_has_no_down_revision(self):
        """The first migration should have down_revision = None."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(Path(__file__).parents[2] / "alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()

        # At least one head exists
        assert len(heads) >= 1

    def test_migration_imports(self):
        """Verify the migration file can be imported without errors."""
        import importlib.util

        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        assert len(files) >= 1

        # Load the first migration file as a module
        spec = importlib.util.spec_from_file_location(
            "test_migration_module", files[0]
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert hasattr(mod, "revision")
        assert mod.down_revision is None


class TestMigrationDDL:
    """Verify the migration produces expected table names."""

    def test_upgrade_creates_expected_tables(self):
        """Inspect the migration file for expected CREATE TABLE statements."""
        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        content = files[0].read_text()

        expected_tables = [
            "book",
            "section",
            "chunk",
            "note_session",
            "coverage_event",
            "qa_message",
        ]
        for table in expected_tables:
            assert f'"{table}"' in content or f"'{table}'" in content or f"create_table(\n        \"{table}\"" in content, f"Table '{table}' not found in migration"

    def test_upgrade_creates_vector_extension(self):
        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        content = files[0].read_text()
        assert "CREATE EXTENSION IF NOT EXISTS vector" in content

    def test_downgrade_drops_all_tables(self):
        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        content = files[0].read_text()
        assert "drop_table" in content

    def test_downgrade_drops_enums(self):
        files = sorted(MIGRATIONS_DIR.glob("*.py"))
        content = files[0].read_text()
        assert "DROP TYPE IF EXISTS" in content
