"""Tests for parsing single-release changelog fragments."""

import pytest

from distlift.changelog.formatter import render_release_entry
from distlift.changelog.models import ChangelogReleaseEntry, ChangelogSection
from distlift.changelog.parser import parse_release_entry_markdown
from distlift.errors import ChangelogError


class TestParseReleaseEntryMarkdown:
    """Exercise ``parse_release_entry_markdown`` validation paths."""

    def test_parses_one_release_block(self) -> None:
        """Accept a minimal fragment matching formatter output."""
        text = "## [1.2.3] - 2024-06-01\n\n### Added\n\n- hello\n"
        entry = parse_release_entry_markdown(text)

        assert entry.version_label == "1.2.3"
        assert entry.date_iso == "2024-06-01"
        assert entry.sections == [
            ChangelogSection(title="Added", bullets=["hello"])
        ]

    def test_allows_leading_blank_lines(self) -> None:
        """Ignore whitespace-only preamble before the heading."""
        text = "\n\n## [0.1.0]\n\n### Fixed\n\n- x\n"
        entry = parse_release_entry_markdown(text)

        assert entry.version_label == "0.1.0"

    def test_accepts_markdown_escaped_open_bracket_in_heading(self) -> None:
        """Accept escaped ``[`` after ``##`` (Markdown tooling / editors)."""
        text = "## \\[0.1.2] - 2026-05-13\n\n### Added\n\n- x\n"
        entry = parse_release_entry_markdown(text)

        assert entry.version_label == "0.1.2"
        assert entry.date_iso == "2026-05-13"

    def test_rejects_multiple_release_headings(self) -> None:
        """Fragments must contain exactly one ``##`` release section."""
        text = "## [1.0.0]\n\n### Added\n\n- a\n\n## [2.0.0]\n"

        with pytest.raises(ChangelogError):
            parse_release_entry_markdown(text)

    def test_rejects_preamble_before_heading(self) -> None:
        """Non-blank lines before the release heading are invalid."""
        text = "note\n## [1.0.0]\n"

        with pytest.raises(ChangelogError):
            parse_release_entry_markdown(text)

    def test_rejects_empty_fragment(self) -> None:
        """Whitespace-only buffers cannot be parsed."""
        with pytest.raises(ChangelogError):
            parse_release_entry_markdown("   \n")

    def test_matches_round_trip_model(self) -> None:
        """Structured release entries survive text round-trip."""
        original = ChangelogReleaseEntry(
            version_label="2.0.0",
            date_iso="2030-01-15",
            sections=[
                ChangelogSection(title="Changed", bullets=["tweak"]),
            ],
            link_ref="2.0.0",
        )
        text = render_release_entry(original)
        parsed = parse_release_entry_markdown(text)

        assert parsed.version_label == original.version_label
        assert parsed.date_iso == original.date_iso
        assert parsed.sections[0].title == "Changed"
        assert parsed.sections[0].bullets == ["tweak"]
