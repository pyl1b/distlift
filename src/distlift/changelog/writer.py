"""Persist formatted changelog documents."""

from __future__ import annotations

from pathlib import Path

from distlift.changelog.formatter import render_changelog_document
from distlift.changelog.models import ChangelogDocument


def write_changelog_document(path: Path, document: ChangelogDocument) -> None:
    """Write a changelog Markdown file with parent directories created.

    Args:
        path: Destination path for the serialized Markdown text.
        document: Structured changelog content to render.
    """
    rendered = render_changelog_document(document)

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(rendered, encoding="utf-8", newline="\n")
