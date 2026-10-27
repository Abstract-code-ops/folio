"""Revision-chain checks for the Alembic migrations (plan unit U6).

Two heads would make `alembic upgrade head` ambiguous, so the chain is
asserted to stay linear. Nothing here executes DDL: the revision graph is read
from the script directory, and the files are only imported.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).parents[2]
MIGRATIONS_DIR = API_ROOT / "alembic" / "versions"


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))


def test_there_is_exactly_one_head() -> None:
    heads = _script().get_heads()
    assert len(heads) == 1, f"migration branches found: {heads}"


def test_the_chain_is_linear_from_head_to_base() -> None:
    revisions = list(_script().walk_revisions())  # head -> base

    assert len(revisions) >= 3
    for newer, older in zip(revisions, revisions[1:]):
        assert newer.down_revision == older.revision, (
            f"{newer.revision} does not point at {older.revision}"
        )
    assert revisions[-1].down_revision is None, "the base revision must have no parent"


def test_the_chunk_page_revision_is_chained_onto_0002() -> None:
    revision = _script().get_revision("0003")

    assert revision is not None
    assert revision.down_revision == "0002"


def test_every_migration_file_imports_and_exposes_its_hooks() -> None:
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert hasattr(module, "upgrade"), f"{path.name} has no upgrade()"
        assert hasattr(module, "downgrade"), f"{path.name} has no downgrade()"
        assert hasattr(module, "revision"), f"{path.name} has no revision id"
