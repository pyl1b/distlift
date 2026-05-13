"""Structured changelog documents independent of Markdown serialization."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.vcs.git import GitCommitRecord

CommitInfo = GitCommitRecord


@attrs.define
class ChangelogSection:
    """One Keep a Changelog subsection such as ``### Added``.

    Attributes:
        title: Visible heading without ``###`` (for example ``Added``).
        bullets: Bullet lines without leading ``- `` (trimmed body text).
    """

    title: str
    bullets: list[str]


@attrs.define
class ChangelogReleaseEntry:
    """One ``## [version]`` block including nested sections.

    Attributes:
        version_label: Text inside brackets for the heading (for example
            ``Unreleased`` or ``1.2.3``).
        date_iso: Optional ISO date suffix rendered after the heading.
        sections: Ordered ``###`` sections under this release.
        link_ref: Lowercase reference label used for footer links
            (for example ``unreleased`` or ``1.2.3``).
    """

    version_label: str
    date_iso: str | None
    sections: list[ChangelogSection]
    link_ref: str


@attrs.define
class ChangelogDocument:
    """Full parsed changelog content prior to rendering.

    Attributes:
        title_line: Top-level Markdown title including ``# `` prefix text.
        intro_lines: Non-heading preamble lines (paragraphs and blanks).
        releases: Ordered ``##`` release blocks (typically unreleased first).
        footer_links: Mapping of reference keys (for example ``unreleased``)
            to link targets at the bottom of the file.
    """

    title_line: str
    intro_lines: list[str]
    releases: list[ChangelogReleaseEntry]
    footer_links: dict[str, str]


@attrs.define
class ChangelogUpdatePlan:
    """Computed changelog write for one package root.

    Attributes:
        path: Absolute ``CHANGELOG.md`` path to create or update.
        inserted_release: Release entry generated for this run.
        new_document: Full document after insertion and footer refresh.
        unreleased_placeholder: Empty unreleased sections left after promotion.
    """

    path: Path
    inserted_release: ChangelogReleaseEntry
    new_document: ChangelogDocument
    unreleased_placeholder: ChangelogReleaseEntry
