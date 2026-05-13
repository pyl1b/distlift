"""Tests for changelog writer utilities."""

from pathlib import Path

from distlift.changelog.formatter import render_changelog_document
from distlift.changelog.models import ChangelogDocument
from distlift.changelog.writer import write_changelog_document


def test_write_changelog_document_round_trip(tmp_path: Path) -> None:
    """Write structured changelog Markdown to disk."""
    doc = ChangelogDocument(
        title_line="# Log",
        intro_lines=[],
        releases=[],
        footer_links={},
    )

    target = tmp_path / "CHANGELOG.md"

    write_changelog_document(target, doc)

    assert target.read_text(encoding="utf-8") == render_changelog_document(doc)
