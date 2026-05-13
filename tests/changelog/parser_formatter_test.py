"""Tests for changelog Markdown parsing and rendering."""

from distlift.changelog.formatter import render_changelog_document
from distlift.changelog.parser import parse_changelog_document


class TestChangelogParserFormatterRoundTrip:
    """Round-trip tests between parser and formatter."""

    def test_parse_and_render_minimal_release(self) -> None:
        """Preserve structure through parse then render."""
        text = (
            "# Title\n"
            "\n"
            "Intro line.\n"
            "\n"
            "## [Unreleased]\n"
            "\n"
            "### Added\n"
            "\n"
            "- Item one\n"
        )

        doc = parse_changelog_document(text)

        assert doc.title_line == "# Title"
        assert "Intro line." in doc.intro_lines
        assert doc.releases[0].version_label == "Unreleased"
        assert doc.releases[0].sections[0].bullets == ["Item one"]

        rendered = render_changelog_document(doc)

        assert "# Title" in rendered
        assert "## [Unreleased]" in rendered
        assert "- Item one" in rendered
