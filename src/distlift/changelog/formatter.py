"""Render changelog documents as Markdown."""

from __future__ import annotations

from distlift.changelog.models import ChangelogDocument, ChangelogReleaseEntry

_STANDARD_SECTION_ORDER: tuple[str, ...] = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)


def _sort_sections(
    entry: ChangelogReleaseEntry,
) -> list[tuple[str, list[str]]]:
    """Return ``(title, bullets)`` pairs in canonical Keep a Changelog order.

    Args:
        entry: Release whose sections should be ordered for rendering.
    """
    by_title = {sec.title: list(sec.bullets) for sec in entry.sections}
    ordered: list[tuple[str, list[str]]] = []

    for title in _STANDARD_SECTION_ORDER:
        if title in by_title and by_title[title]:
            ordered.append((title, by_title.pop(title)))

    for title in sorted(by_title.keys()):
        bullets = by_title[title]

        if bullets:
            ordered.append((title, bullets))

    return ordered


def _content_intro_lines(intro_lines: list[str]) -> list[str]:
    """Return preamble lines with outer blank lines removed.

    Blank-only ``intro_lines`` entries come from the single separator
    between the document title and the first ``##`` release heading during
    parse; they must not be re-emitted as extra blank lines on render.

    Args:
        intro_lines: Non-heading lines between the title and first release.
    """
    trimmed = [line.rstrip("\n") for line in intro_lines]

    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)

    while trimmed and not trimmed[-1].strip():
        trimmed.pop()

    return trimmed


def render_release_entry(entry: ChangelogReleaseEntry) -> str:
    """Render a single ``##`` release block including ``###`` sections.

    Args:
        entry: Parsed release entry from the document model.
    """
    lines: list[str] = []

    if entry.date_iso:
        lines.append(f"## [{entry.version_label}] - {entry.date_iso}")
    else:
        lines.append(f"## [{entry.version_label}]")

    lines.append("")

    pairs = _sort_sections(entry)

    if not pairs:
        return "\n".join(lines).rstrip() + "\n"

    for idx, (title, bullets) in enumerate(pairs):
        if idx > 0:
            lines.append("")

        lines.append(f"### {title}")
        lines.append("")

        for bullet in bullets:
            lines.append(f"- {bullet}")

    return "\n".join(lines).rstrip() + "\n"


def render_changelog_document(doc: ChangelogDocument) -> str:
    """Serialize a full changelog document with footer reference links.

    Args:
        doc: Structured changelog prior to writing disk.
    """
    lines: list[str] = []

    lines.append(doc.title_line.strip())
    lines.append("")

    content_intro = _content_intro_lines(doc.intro_lines)

    for intro in content_intro:
        lines.append(intro.rstrip("\n"))

    if content_intro:
        lines.append("")

    for idx, rel in enumerate(doc.releases):
        if idx > 0:
            lines.append("")

        lines.append(render_release_entry(rel).rstrip("\n"))

    if doc.footer_links:
        lines.append("")

        for key in sorted(doc.footer_links.keys()):
            url = doc.footer_links[key]
            lines.append(f"[{key}]: {url}")

    body = "\n".join(lines).rstrip() + "\n"

    return body
