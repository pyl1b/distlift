from __future__ import annotations

from pathlib import Path

from distlift.config.models import ManagedPackageConfig
from distlift.logging_utils import get_logger
from distlift.vcs.git import GitRepository
from distlift.vcs.tags import find_latest_tag_for_package

log = get_logger(__name__)


def find_package_last_tag(
    package: ManagedPackageConfig,
    tags: list[str],
) -> str | None:
    template = package.tag_template or f"v{{version}}-{package.name}"
    fmt = package.version_format
    return find_latest_tag_for_package(tags, template, fmt, package.name)


def package_has_changes_since_tag(
    package: ManagedPackageConfig,
    tag: str | None,
    git: GitRepository,
) -> bool:
    pkg_path = Path(package.path)
    if tag is None:
        # No tag means treat as fully changed
        return True

    try:
        changed = git.get_changed_files(revspec=f"{tag}..HEAD")
    except Exception as exc:
        log.warning(
            "Could not detect changes for %s since %s: %s",
            package.name,
            tag,
            exc,
        )
        return True

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
    """Return packages with changes since their last tag."""
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
