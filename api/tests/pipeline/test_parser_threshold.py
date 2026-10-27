"""Tests that the parser reads the connective threshold from settings (U3).

The threshold used to be a module constant (`CONNECTIVE_THRESHOLD = 150`)
while `settings.connective_word_count_threshold` sat unread, so the
documented knob did nothing.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.pipeline.parser import _is_connective


def test_default_threshold_comes_from_settings() -> None:
    assert settings.connective_word_count_threshold == 150
    assert _is_connective(149) is True
    assert _is_connective(150) is False
    assert _is_connective(151) is False


def test_threshold_follows_a_settings_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "connective_word_count_threshold", 10)

    assert _is_connective(9) is True
    assert _is_connective(10) is False


def test_a_zero_word_section_is_connective() -> None:
    assert _is_connective(0) is True
