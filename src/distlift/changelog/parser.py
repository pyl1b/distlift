"""Parse Keep a Changelog Markdown into structured models."""

from __future__ import annotations

import re

from distlift.changelog.models import (
    ChangelogDocument,
    ChangelogReleaseEntry,
    ChangelogSection,
)
from distlift.errors import ChangelogError

_FOOTER_LINK_RE = re.compile(r"^\[([^\]]+)\]:\s*(.+)$")
_RELEASE_HEAD_RE = re.compile(
    r"^## \[(?P<ver>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?$"
)


def _extract_footer(
    lines: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Split trailing reference-link definitions from body lines.

    Args:
        lines: Complete file split into logical lines without final newline.
    """
    footer: dict[str, str] = {}
    idx = len(lines) - 1

    while idx >= 0 and not lines[idx].strip():
        idx -= 1

    while idx >= 0:
        stripped = lines[idx].strip()
        match = _FOOTER_LINK_RE.match(stripped)

        if match is None:
            break

        key = match.group(1).strip().lower()
        footer[key] = match.group(2).strip()
        idx -= 1

        while idx >= 0 and not lines[idx].strip():
            idx -= 1

    return lines[: idx + 1], footer


def _parse_release_block(block_lines: list[str]) -> ChangelogReleaseEntry:
    """Parse one ``##`` release subsection into a structured entry.

    Args:
        block_lines: Lines beginning with the ``##`` heading for this release.
    """
    if not block_lines:
        raise ChangelogError("Empty changelog release block")

    head_match = _RELEASE_HEAD_RE.match(block_lines[0].strip())

    if head_match is None:
        raise ChangelogError(
            f"Malformed changelog release heading: {block_lines[0]!r}"
        )

    version_label = head_match.group("ver").strip()
    date_iso = head_match.group("date")
    link_ref = version_label.strip().lower()

    sections: list[ChangelogSection] = []
    current_title: str | None = None
    current_bullets: list[str] = []

    def _flush_section() -> None:
        nonlocal current_title, current_bullets

        if current_title is None:
            current_bullets = []

            return

        sections.append(
            ChangelogSection(
                title=current_title, bullets=list(current_bullets)
            )
        )
        current_title = None
        current_bullets = []

    for raw_line in block_lines[1:]:
        line = raw_line.rstrip("\n")

        if line.startswith("### "):
            _flush_section()
            current_title = line[4:].strip()

            continue

        stripped = line.strip()

        if stripped.startswith("- "):
            if current_title is None:
                raise ChangelogError(
                    "Bullet found before any ### section under "
                    f"[{version_label}]"
                )

            current_bullets.append(stripped[2:].strip())

            continue

        if not stripped:
            continue

        if current_title is not None and current_bullets:
            current_bullets[-1] = current_bullets[-1].rstrip() + " " + stripped

            continue

        raise ChangelogError(
            f"Unexpected line in changelog release [{version_label}]: {line!r}"
        )

    _flush_section()

    return ChangelogReleaseEntry(
        version_label=version_label,
        date_iso=date_iso,
        sections=sections,
        link_ref=link_ref,
    )


def parse_release_entry_markdown(text: str) -> ChangelogReleaseEntry:
    """Parse Markdown containing exactly one ``## [version]`` release block.

    Args:
        text: Fragment shown in an external editor, not a full changelog file.
    """
    # Normalize Windows newlines and strip BOM so heading detection is stable
    raw = text.replace("\r\n", "\n").lstrip("\ufeff")
    raw_stripped = raw.strip()

    if not raw_stripped:
        raise ChangelogError("Changelog release fragment is empty")

    lines = raw_stripped.splitlines()
    start_idx: int | None = None

    for idx, line in enumerate(lines):
        if line.startswith("## "):
            start_idx = idx

            break

        if line.strip():
            raise ChangelogError(
                f"Unexpected text before release heading: {line!r}"
            )

    if start_idx is None:
        raise ChangelogError(
            "Changelog fragment must contain a ## [version] release heading"
        )

    tail = lines[start_idx + 1 :]

    for line in tail:
        if line.startswith("## "):
            raise ChangelogError(
                "Changelog fragment must contain exactly one ## release "
                "heading"
            )

    block_lines = lines[start_idx:]

    return _parse_release_block(block_lines)


def parse_changelog_document(text: str) -> ChangelogDocument:
    """Parse Keep-a-Changelog-style Markdown into a structured document.

    Args:
        text: Full ``CHANGELOG.md`` file contents.
    """
    raw_lines = text.splitlines()
    body_lines, footer_links = _extract_footer(raw_lines)

    heading_idxs = [
        idx for idx, line in enumerate(body_lines) if line.startswith("## ")
    ]

    if not heading_idxs:
        intro_chunk = body_lines

        if intro_chunk and intro_chunk[0].startswith("#"):
            title_line = intro_chunk[0].strip()
            intro_rest = intro_chunk[1:]
        else:
            title_line = "# Changelog"
            intro_rest = list(intro_chunk)

        return ChangelogDocument(
            title_line=title_line,
            intro_lines=intro_rest,
            releases=[],
            footer_links=footer_links,
        )

    intro_lines_raw = body_lines[: heading_idxs[0]]

    if intro_lines_raw and intro_lines_raw[0].startswith("#"):
        title_line = intro_lines_raw[0].strip()
        intro_rest = intro_lines_raw[1:]
    else:
        title_line = "# Changelog"
        intro_rest = list(intro_lines_raw)

    releases: list[ChangelogReleaseEntry] = []

    for hi, start in enumerate(heading_idxs):
        end = (
            heading_idxs[hi + 1]
            if hi + 1 < len(heading_idxs)
            else len(body_lines)
        )
        block = body_lines[start:end]
        releases.append(_parse_release_block(block))

    return ChangelogDocument(
        title_line=title_line,
        intro_lines=intro_rest,
        releases=releases,
        footer_links=footer_links,
    )
