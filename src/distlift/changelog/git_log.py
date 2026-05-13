"""Helpers for collecting formatted commits between revisions."""

from __future__ import annotations

from distlift.vcs.git import GitCommitRecord, GitRepository


def collect_commits(
    repo: GitRepository,
    last_tag: str | None,
    package_path: str | None,
) -> list[GitCommitRecord]:
    """Return commits between ``last_tag`` and ``HEAD``, optionally scoped.

    Args:
        repo: Repository wrapper bound at the workspace root.
        last_tag: Exclusive lower bound tag name, or None for full history.
        package_path: Optional repo-relative directory limiting paths.
    """
    revspec = f"{last_tag}..HEAD" if last_tag else None

    posix_path = None

    if package_path:
        posix_path = package_path.replace("\\", "/").strip("/")

        if not posix_path:
            posix_path = None

    return repo.list_commits_between(revspec, posix_path)
