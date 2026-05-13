"""Detect which managed monorepo packages have commits since their last tag."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import ManagedPackageConfig
from distlift.errors import GitStateError
from distlift.logging_utils import get_logger
from distlift.vcs.git import GitRepository
from distlift.vcs.tags import find_latest_tag_for_package

log = get_logger(__name__)


def find_package_last_tag(
    package: ManagedPackageConfig,
    tags: list[str],
) -> str | None:
    """Return the newest tag that encodes ``package``'s current version.

    Args:
        package: Managed package metadata including name and templates.
        tags: All local tag names from Git.

    Returns:
        The latest matching tag, or None when none parse successfully.
    """
    template = package.tag_template or f"v{{version}}-{package.name}"
    fmt = package.version_format

    return find_latest_tag_for_package(tags, template, fmt, package.name)


def package_has_changes_since_tag(
    package: ManagedPackageConfig,
    tag: str | None,
    git: GitRepository,
) -> bool:
    """Return True when ``git diff`` shows paths under the package directory.

    Args:
        package: Managed package whose relative ``path`` is inspected.
        tag: Previous release tag, or None to treat the package as changed.
        git: Repository handle used to list changed paths.

    Returns:
        True when the package subtree differs since ``tag``, when ``tag`` is
        missing, or when change detection fails conservatively.
    """
    pkg_path = Path(package.path)

    if tag is None:
        # Without a baseline tag the package is always eligible for release
        return True

    try:
        changed = git.get_changed_files(revspec=f"{tag}..HEAD")
    except GitStateError as exc:
        log.warning(
            "Could not detect changes for %s since %s: %s",
            package.name,
            tag,
            exc,
        )
        return True

    # Any changed file inside the package subtree counts as a content change
    for f in changed:
        try:
            f.relative_to(git.root / pkg_path)
            return True
        except ValueError:
            continue

    return False


def find_changed_packages(
    packages: list[ManagedPackageConfig],
    tags: list[str],
    git: GitRepository,
    selected_names: list[str] | None = None,
) -> list[ManagedPackageConfig]:
    """Return packages whose trees differ from their latest version tag.

    Args:
        packages: Full managed package list from configuration.
        tags: All local tag names from Git.
        git: Repository handle for diff queries.
        selected_names: Optional filter restricting output to these names.

    Returns:
        Packages with commits since their last tag (or with no prior tag).
    """
    result = []

    for pkg in packages:
        if selected_names and pkg.name not in selected_names:
            continue

        last_tag = find_package_last_tag(pkg, tags)

        if package_has_changes_since_tag(pkg, last_tag, git):
            log.info(
                "Package '%s' has changes since %s",
                pkg.name,
                last_tag or "<no tag>",
            )
            result.append(pkg)
        else:
            log.debug("Package '%s' is up to date at %s", pkg.name, last_tag)

    return result
