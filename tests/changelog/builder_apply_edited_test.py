"""Tests for merging editor output back into changelog plans."""

from pathlib import Path

import pytest

from distlift.changelog.builder import (
    apply_edited_release_to_plan,
    validate_edited_release_version_label,
)
from distlift.changelog.models import (
    ChangelogDocument,
    ChangelogReleaseEntry,
    ChangelogSection,
    ChangelogUpdatePlan,
)
from distlift.errors import ChangelogError


def _entry(
    ver: str,
    bullets: list[str],
    *,
    date_iso: str | None = "2020-01-01",
) -> ChangelogReleaseEntry:
    """Build a tiny release entry for structural tests.

    Args:
        ver: Version label inside the simulated heading.
        bullets: Bullets placed under ``### Added``.
        date_iso: Optional ISO date string for the heading line.
    """
    return ChangelogReleaseEntry(
        version_label=ver,
        date_iso=date_iso,
        sections=[
            ChangelogSection(title="Added", bullets=list(bullets)),
        ],
        link_ref=ver.strip().lower(),
    )


def test_apply_edited_with_unreleased_prefix(tmp_path: Path) -> None:
    """Replace the staged release when an ``[Unreleased]`` row precedes it."""
    inserted = _entry("1.0.0", ["orig"])
    unreleased = ChangelogReleaseEntry(
        version_label="Unreleased",
        date_iso=None,
        sections=[],
        link_ref="unreleased",
    )
    doc = ChangelogDocument(
        title_line="# Test",
        intro_lines=[],
        releases=[unreleased, inserted],
        footer_links={},
    )
    plan = ChangelogUpdatePlan(
        path=tmp_path / "CHANGELOG.md",
        inserted_release=inserted,
        new_document=doc,
        unreleased_placeholder=unreleased,
    )
    edited = _entry("1.0.0", ["edited"])

    out = apply_edited_release_to_plan(plan, edited)

    assert out.new_document.releases[0] is unreleased
    assert out.new_document.releases[1].sections[0].bullets == ["edited"]
    assert out.inserted_release.sections[0].bullets == ["edited"]


def test_apply_edited_without_unreleased(tmp_path: Path) -> None:
    """Replace the only release row when no unreleased placeholder exists."""
    inserted = _entry("2.1.0", ["a"])
    doc = ChangelogDocument(
        title_line="# T",
        intro_lines=[],
        releases=[inserted],
        footer_links={},
    )
    plan = ChangelogUpdatePlan(
        path=tmp_path / "CHANGELOG.md",
        inserted_release=inserted,
        new_document=doc,
        unreleased_placeholder=ChangelogReleaseEntry(
            version_label="Unreleased",
            date_iso=None,
            sections=[],
            link_ref="unreleased",
        ),
    )
    edited = _entry("2.1.0", ["b"])

    out = apply_edited_release_to_plan(plan, edited)

    assert len(out.new_document.releases) == 1
    assert out.new_document.releases[0].sections[0].bullets == ["b"]


def test_validate_edited_version_rejects_rename() -> None:
    """Users must keep the planned ``## [version]`` token unchanged."""
    edited = _entry("9.9.9", ["x"])

    with pytest.raises(ChangelogError):
        validate_edited_release_version_label(edited, "1.0.0")


def test_apply_missing_slot_raises(tmp_path: Path) -> None:
    """Fail loudly when the staged document no longer matches the plan."""
    inserted = _entry("1.0.0", ["x"])
    other = _entry("9.0.0", ["y"])
    doc = ChangelogDocument(
        title_line="# T",
        intro_lines=[],
        releases=[other],
        footer_links={},
    )
    plan = ChangelogUpdatePlan(
        path=tmp_path / "CHANGELOG.md",
        inserted_release=inserted,
        new_document=doc,
        unreleased_placeholder=inserted,
    )

    with pytest.raises(ChangelogError):
        apply_edited_release_to_plan(plan, inserted)
