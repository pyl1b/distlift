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

    def test_render_is_idempotent_for_title_separator(self) -> None:
        """Parse/render cycles must not accumulate blank lines after the title."""
        text = (
            "# Changelog\n"
            "\n"
            "## [Unreleased]\n"
            "\n"
            "## [1.0.0] - 2024-01-01\n"
            "\n"
            "### Added\n"
            "\n"
            "- Item one\n"
        )

        doc = parse_changelog_document(text)
        rendered = render_changelog_document(doc)
        again = render_changelog_document(parse_changelog_document(rendered))

        assert rendered == again
        assert rendered.startswith("# Changelog\n\n## [Unreleased]")
