"""Conventional Commits parsing for changelog routing."""

from __future__ import annotations

import re

import attrs

_CC_HEADER = re.compile(
    r"^(?P<type>[a-zA-Z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<bang>!)?:\s*"
    r"(?P<desc>.+)$"
)


@attrs.define(frozen=True)
class ConventionalCommit:
    """Structured view of a commit subject/body pair.

    Attributes:
        raw_subject: Original first-line subject text from Git.
        raw_body: Remaining body lines from Git (may be empty).
        type: Lowercase conventional type token when parsed, else None.
        scope: Optional scope text between parentheses.
        breaking: True when ``!`` or a breaking-change footer is present.
        description: Human-readable summary without type prefix when parsed,
            else the trimmed raw subject.
    """

    raw_subject: str
    raw_body: str

    type: str | None
    scope: str | None
    breaking: bool
    description: str


def _footer_breaking(body: str) -> bool:
    """Return True when the body advertises a breaking change footer.

    Args:
        body: Commit body text possibly containing footers.
    """
    for raw_line in body.splitlines():
        line = raw_line.strip()

        if line.upper().startswith("BREAKING CHANGE"):
            return True

        if line.upper().startswith("BREAKING-CHANGE"):
            return True

    return False


def parse_conventional_commit(subject: str, body: str) -> ConventionalCommit:
    """Parse ``type(scope)!: description`` plus breaking footers.

    Args:
        subject: Commit subject line from Git.
        body: Commit body text following the subject line.
    """
    subj = subject.strip()
    bod = body or ""

    match = _CC_HEADER.match(subj)

    if match is None:
        footer_break = _footer_breaking(bod)

        return ConventionalCommit(
            raw_subject=subj,
            raw_body=bod,
            type=None,
            scope=None,
            breaking=footer_break,
            description=subj,
        )

    ctype = match.group("type").lower()
    scope = match.group("scope")
    bang = match.group("bang")
    desc = match.group("desc").strip()
    footer_break = _footer_breaking(bod)
    breaking = bool(bang) or footer_break

    return ConventionalCommit(
        raw_subject=subj,
        raw_body=bod,
        type=ctype,
        scope=scope,
        breaking=breaking,
        description=desc,
    )
