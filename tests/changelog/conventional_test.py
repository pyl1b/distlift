"""Tests for conventional commit parsing."""

from distlift.changelog.conventional import parse_conventional_commit


class TestParseConventionalCommit:
    """Grouping tests for ``parse_conventional_commit``."""

    def test_feat_scope(self) -> None:
        """Parse type and scope from a conventional header."""
        cc = parse_conventional_commit("feat(api): hello world", "")

        assert cc.type == "feat"
        assert cc.scope == "api"
        assert cc.description == "hello world"
        assert not cc.breaking

    def test_breaking_bang(self) -> None:
        """Treat ``!`` after the type as a breaking change."""
        cc = parse_conventional_commit("feat!: break things", "")

        assert cc.breaking

    def test_footer_breaking_change(self) -> None:
        """Detect breaking footers in the commit body."""
        body = "details\n\nBREAKING CHANGE: bye\n"
        cc = parse_conventional_commit("chore: tweak", body)

        assert cc.breaking

    def test_non_conventional_subject(self) -> None:
        """Return uncategorized commits with the raw subject."""
        cc = parse_conventional_commit("just a note", "")

        assert cc.type is None
        assert cc.description == "just a note"
