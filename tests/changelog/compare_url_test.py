"""Tests for deriving compare URL templates from Git remotes."""

import pytest

from distlift.changelog.compare_url import derive_compare_url_template


@pytest.mark.parametrize(
    ("remote", "expected_suffix"),
    [
        (
            "git@github.com:acme/widget.git",
            "https://github.com/acme/widget/compare/{prev}...{next}",
        ),
        (
            "https://github.com/acme/widget.git",
            "https://github.com/acme/widget/compare/{prev}...{next}",
        ),
        (
            "git@gitlab.com:grp/sub/widget.git",
            "https://gitlab.com/grp/sub/widget/-/compare/{prev}...{next}",
        ),
        (
            "git@bitbucket.org:acme/widget.git",
            "https://bitbucket.org/acme/widget/branches/compare/{next}..{prev}",
        ),
    ],
)
def test_known_hosts(remote: str, expected_suffix: str) -> None:
    """Map known Git host SSH/HTTPS URLs to compare templates."""
    got = derive_compare_url_template(remote)

    assert got == expected_suffix


def test_unknown_scheme_returns_none() -> None:
    """Return ``None`` when the remote cannot be classified."""
    assert (
        derive_compare_url_template("ssh://git@example.com/proj.git") is None
    )
