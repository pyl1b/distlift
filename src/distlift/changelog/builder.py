"""Build changelog update plans from Git history and configuration."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import attrs

from distlift.changelog.compare_url import resolve_compare_url_template
from distlift.changelog.conventional import parse_conventional_commit
from distlift.changelog.formatter import render_release_entry
from distlift.changelog.git_log import collect_commits
from distlift.changelog.models import (
    ChangelogDocument,
    ChangelogReleaseEntry,
    ChangelogSection,
    ChangelogUpdatePlan,
)
from distlift.changelog.parser import parse_changelog_document
from distlift.config.models import ChangelogConfig
from distlift.errors import ChangelogError
from distlift.logging_utils import get_logger
from distlift.vcs.git import GitRepository

log = get_logger(__name__)

_SECTION_ORDER: tuple[str, ...] = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)


def _normalize_skip(types: list[str]) -> set[str]:
    """Lower-case conventional types configured for omission.

    Args:
        types: Raw skip list from configuration.
    """
    return {t.strip().lower() for t in types if t.strip()}


def _norm_key(text: str) -> str:
    """Normalize bullet text for deduplication comparisons.

    Args:
        text: Raw bullet body without the leading hyphen.
    """
    return " ".join(text.split()).strip().lower()


def _mapping_lookup(cfg: ChangelogConfig, ctype: str | None) -> str:
    """Resolve a conventional type to a Keep a Changelog section title.

    Args:
        cfg: Effective changelog configuration for this repository.
        ctype: Parsed conventional type token, if any.
    """
    if ctype is None:
        return cfg.default_section

    lowered = ctype.lower()
    table = {k.lower(): v for k, v in cfg.commit_mapping.items()}

    return table.get(lowered, cfg.default_section)


def _bullet_text(conv: object) -> str:
    """Format changelog bullet text including breaking annotations.

    Args:
        conv: Parsed ``ConventionalCommit`` instance from this package.
    """
    desc = conv.description  # type: ignore[attr-defined]

    if conv.breaking:  # type: ignore[attr-defined]
        return f"**BREAKING:** {desc}"

    return str(desc)


def _commits_to_section_map(
    repo: GitRepository,
    last_tag: str | None,
    package_path: str | None,
    cfg: ChangelogConfig,
) -> dict[str, list[str]]:
    """Group filtered commits into changelog section buckets.

    Args:
        repo: Repository whose history should be scanned.
        last_tag: Exclusive lower bound tag, if any.
        package_path: Optional path filter for monorepo packages.
        cfg: Effective changelog configuration.
    """
    skip_types = _normalize_skip(cfg.skip_commit_types)
    commits = collect_commits(repo, last_tag, package_path)
    buckets: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    for record in commits:
        conv = parse_conventional_commit(record.subject, record.body)

        if conv.type and conv.type.lower() in skip_types:
            continue

        section_title = _mapping_lookup(cfg, conv.type)
        bullet = _bullet_text(conv)
        norm = _norm_key(bullet)
        dedupe = seen.setdefault(section_title, set())

        if norm in dedupe:
            continue

        dedupe.add(norm)
        buckets.setdefault(section_title, []).append(bullet)

    return buckets


def _release_sections_to_map(
    release: ChangelogReleaseEntry,
) -> dict[str, list[str]]:
    """Flatten structured sections into a mutable bullet map.

    Args:
        release: Parsed release containing ``###`` sections.
    """
    out: dict[str, list[str]] = {}

    for sec in release.sections:
        out.setdefault(sec.title, []).extend(sec.bullets)

    return out


def _merge_bullet_maps(
    *maps: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge bullet maps while deduplicating per section.

    Args:
        maps: One or more section maps merged in argument order.
    """
    merged: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}

    for m in maps:
        for title, bullets in m.items():
            bucket = merged.setdefault(title, [])
            dedupe = seen.setdefault(title, set())

            for bullet in bullets:
                key = _norm_key(bullet)

                if key in dedupe:
                    continue

                dedupe.add(key)
                bucket.append(bullet)

    return merged


def _dict_to_sections(
    section_map: dict[str, list[str]],
) -> list[ChangelogSection]:
    """Convert an unordered map into ordered ``ChangelogSection`` rows.

    Args:
        section_map: Mapping of Keep a Changelog titles to bullet lists.
    """
    sections: list[ChangelogSection] = []

    for title in _SECTION_ORDER:
        bullets = section_map.get(title)

        if bullets:
            sections.append(
                ChangelogSection(title=title, bullets=list(bullets))
            )

    extras = sorted(k for k in section_map.keys() if k not in _SECTION_ORDER)

    for title in extras:
        bullets = section_map[title]

        if bullets:
            sections.append(
                ChangelogSection(title=title, bullets=list(bullets))
            )

    return sections


def _split_unreleased(
    doc: ChangelogDocument,
) -> tuple[dict[str, list[str]], list[ChangelogReleaseEntry]]:
    """Separate manual unreleased bullets from frozen historical releases.

    Args:
        doc: Parsed changelog prior to this release cut.
    """
    manual: dict[str, list[str]] = {}
    tail: list[ChangelogReleaseEntry] = []

    for rel in doc.releases:
        if rel.link_ref == "unreleased":
            manual = _merge_bullet_maps(manual, _release_sections_to_map(rel))

            continue

        tail.append(rel)

    return manual, tail


def _empty_document(cfg: ChangelogConfig) -> ChangelogDocument:
    """Create a scaffold document when no changelog file exists yet.

    Args:
        cfg: Effective changelog configuration describing defaults.
    """
    title = cfg.title.strip() if cfg.title.strip() else "Changelog"
    title_line = f"# {title}"
    intro_lines: list[str] = []

    if cfg.header_text.strip():
        intro_lines.extend(cfg.header_text.strip().splitlines())

    return ChangelogDocument(
        title_line=title_line,
        intro_lines=intro_lines,
        releases=[],
        footer_links={},
    )


def _refresh_footer_links(
    prior: dict[str, str],
    compare_tpl: str | None,
    *,
    last_tag: str | None,
    new_tag: str,
    new_version_label: str,
    root_sha: str | None,
) -> dict[str, str]:
    """Rewrite comparison URLs for unreleased and the newest version entry.

    Args:
        prior: Existing footer reference definitions keyed in lowercase.
        compare_tpl: Template containing ``{prev}`` and ``{next}``, if any.
        last_tag: Previous release tag name used as compare baseline.
        new_tag: Tag created by this release plan.
        new_version_label: Version text inside brackets for the heading.
        root_sha: Root commit hash when no ``last_tag`` exists.
    """
    links = dict(prior)

    if compare_tpl is None:
        return links

    anchor_prev = last_tag or root_sha or ""

    if not anchor_prev:
        log.debug(
            "Skipping changelog compare links because no previous ref exists",
        )

        return links

    ver_key = new_version_label.strip().lower()

    try:
        links[ver_key] = compare_tpl.format(prev=anchor_prev, next=new_tag)
        links["unreleased"] = compare_tpl.format(prev=new_tag, next="HEAD")
    except KeyError as exc:
        raise ChangelogError(
            "changelog compare URL template must contain {prev} and {next}"
        ) from exc

    return links


def build_changelog_update_plan(
    repo: GitRepository,
    changelog_path: Path,
    package_path: str | None,
    last_tag: str | None,
    new_version_str: str,
    new_tag_name: str,
    release_date: date,
    config: ChangelogConfig,
) -> ChangelogUpdatePlan:
    """Compute the changelog write performed alongside a release commit.

    Args:
        repo: Git accessor rooted at the workspace.
        changelog_path: Absolute path of the changelog file to write.
        package_path: Repository-relative package directory or None.
        last_tag: Latest applicable release tag before this bump.
        new_version_str: Rendered next semantic version text.
        new_tag_name: Concrete tag ref created for this release.
        release_date: Calendar date recorded next to the version heading.
        config: Effective changelog configuration for formatting rules.
    """
    if changelog_path.exists():
        raw_text = changelog_path.read_text(encoding="utf-8")

        try:
            document = parse_changelog_document(raw_text)
        except ChangelogError as exc:
            log.error(
                "Failed to parse existing changelog at %s: %s",
                changelog_path,
                exc,
            )

            raise
    else:
        document = _empty_document(config)

    unreleased_manual, historical = _split_unreleased(document)
    historical_kept = [
        rel
        for rel in historical
        if rel.version_label.strip().lower() != new_version_str.strip().lower()
    ]

    git_buckets = _commits_to_section_map(
        repo,
        last_tag,
        package_path,
        config,
    )

    combined = _merge_bullet_maps(unreleased_manual, git_buckets)
    inserted_sections = _dict_to_sections(combined)

    date_txt = release_date.strftime(config.date_format)

    inserted_release = ChangelogReleaseEntry(
        version_label=new_version_str,
        date_iso=date_txt,
        sections=inserted_sections,
        link_ref=new_version_str.strip().lower(),
    )

    unreleased_placeholder = ChangelogReleaseEntry(
        version_label="Unreleased",
        date_iso=None,
        sections=[],
        link_ref="unreleased",
    )

    rebuilt_releases: list[ChangelogReleaseEntry] = []

    if config.include_unreleased_section:
        rebuilt_releases.append(unreleased_placeholder)

    rebuilt_releases.append(inserted_release)
    rebuilt_releases.extend(historical_kept)

    remote_url = repo.get_remote_url("origin")
    compare_tpl = resolve_compare_url_template(
        config.compare_url_template,
        remote_url,
    )

    root_sha = repo.get_initial_commit_sha() if last_tag is None else None

    new_footer = _refresh_footer_links(
        document.footer_links,
        compare_tpl,
        last_tag=last_tag,
        new_tag=new_tag_name,
        new_version_label=new_version_str,
        root_sha=root_sha,
    )

    new_document = ChangelogDocument(
        title_line=document.title_line,
        intro_lines=list(document.intro_lines),
        releases=rebuilt_releases,
        footer_links=new_footer,
    )

    log.log(
        5,
        "Prepared changelog entry at %s (%d sections)",
        changelog_path,
        len(inserted_sections),
    )

    return ChangelogUpdatePlan(
        path=changelog_path,
        inserted_release=inserted_release,
        new_document=new_document,
        unreleased_placeholder=unreleased_placeholder,
    )


def validate_edited_release_version_label(
    edited: ChangelogReleaseEntry,
    expected_version_label: str,
) -> None:
    """Ensure the user did not rename the ``## [version]`` heading token.

    Args:
        edited: Parsed release entry produced from editor Markdown.
        expected_version_label: Version bracket text from the release plan.
    """
    got = edited.version_label.strip()
    exp = expected_version_label.strip()

    if got != exp:
        raise ChangelogError(
            f"Edited changelog heading version {got!r} must match "
            f"planned release {exp!r}"
        )


def apply_edited_release_to_plan(
    plan: ChangelogUpdatePlan,
    edited: ChangelogReleaseEntry,
) -> ChangelogUpdatePlan:
    """Swap the generated release entry inside the staged full document.

    Args:
        plan: Original mutation built from Git history.
        edited: Replacement release parsed from user-edited Markdown.
    """
    releases = list(plan.new_document.releases)
    target_link = plan.inserted_release.link_ref
    target_ver = plan.inserted_release.version_label

    match_idx: int | None = None

    for idx, rel in enumerate(releases):
        if rel.link_ref == target_link and rel.version_label == target_ver:
            match_idx = idx

            break

    if match_idx is None:
        raise ChangelogError(
            f"Could not locate planned release [{target_ver}] in changelog "
            "document"
        )

    releases[match_idx] = edited

    new_document = attrs.evolve(plan.new_document, releases=releases)

    return attrs.evolve(
        plan,
        inserted_release=edited,
        new_document=new_document,
    )


def render_inserted_entry_preview(plan: ChangelogUpdatePlan) -> str:
    """Render Markdown for the release entry introduced by ``plan``.

    Args:
        plan: Planned changelog mutation produced for one package.
    """
    return render_release_entry(plan.inserted_release)


def scaffold_initial_changelog_document(
    config: ChangelogConfig,
) -> ChangelogDocument:
    """Create an empty changelog scaffold according to configuration.

    Args:
        config: Changelog-related settings including titles and unreleased
            flag.
    """
    base = _empty_document(config)
    releases: list[ChangelogReleaseEntry] = []

    if config.include_unreleased_section:
        releases.append(
            ChangelogReleaseEntry(
                version_label="Unreleased",
                date_iso=None,
                sections=[],
                link_ref="unreleased",
            )
        )

    return ChangelogDocument(
        title_line=base.title_line,
        intro_lines=list(base.intro_lines),
        releases=releases,
        footer_links={},
    )
