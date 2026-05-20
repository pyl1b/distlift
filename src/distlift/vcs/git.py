"""Subprocess-backed Git repository helper and built-in backend plugin."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import attrs

from distlift.errors import GitStateError
from distlift.logging_utils import get_logger
from distlift.plugins.base import GitBackendPlugin
from distlift.plugins.registry import PluginRegistry

log = get_logger(__name__)

_LOG_FIELD_SEP = "\x1f"
_LOG_RECORD_SEP = "\x1e"
# ``git log`` separates records with ``\\x1e``; parts may use ``\\n``.
# Avoid bare ``str.strip()``: Python treats ``\\x1f`` as whitespace.
_RECORD_CHUNK_STRIP_CHARS = "\r\n\t "


class GitCommitRecord(NamedTuple):
    """One commit row parsed from a formatted ``git log`` invocation.

    Attributes:
        sha_full: Full 40-character hexadecimal object name.
        sha_short: Abbreviated hash suitable for display.
        author: Author name string from Git metadata.
        authored_iso: Strict ISO-like timestamp from ``%ai``.
        subject: First line of the commit message.
        body: Remaining commit message lines after the subject.
    """

    sha_full: str
    sha_short: str
    author: str
    authored_iso: str
    subject: str
    body: str


@attrs.define
class GitRepository:
    """Run ``git`` commands scoped to a single repository root.

    Attributes:
        root: Absolute filesystem path passed to ``git -C`` for every call.
    """

    root: Path

    def _run(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Execute ``git`` with ``-C`` set to ``root`` and capture output.

        Args:
            args: Arguments appended after ``git -C <root>``.
            check: When True, raise ``GitStateError`` for non-zero exits.

        Returns:
            The completed process with text stdout and stderr.
        """
        cmd = ["git", "-C", str(self.root), *args]

        # Record argv at trace level for debugging nested automation flows
        log.log(5, "git %s", " ".join(args))

        result = subprocess.run(
            cmd, check=False, text=True, capture_output=True
        )

        # Surface CLI failures as typed errors for callers to handle uniformly
        if check and result.returncode != 0:
            raise GitStateError(
                f"git {' '.join(args)} failed (exit {result.returncode}):\n"
                f"{result.stderr.strip()}"
            )
        return result

    def ensure_clean_worktree(self) -> None:
        """Raise ``GitStateError`` when the working tree is not clean."""
        # Porcelain output is empty only when there is nothing to commit
        result = self._run(["status", "--porcelain"])

        if result.stdout.strip():
            raise GitStateError(
                "Working tree is not clean. Commit or stash before "
                "releasing.\n" + result.stdout.strip()
            )

    def get_tags(self) -> list[str]:
        """Return every local tag name (unsorted; Git defines no order)."""
        result = self._run(["tag", "--list"])

        return [t for t in result.stdout.splitlines() if t]

    def get_tags_matching(self, pattern: str) -> list[str]:
        """Return tag names matching a ``git tag --list`` glob pattern.

        Args:
            pattern: Glob passed to ``git tag --list`` (for example ``v*``).
        """
        result = self._run(["tag", "--list", pattern])

        return [t for t in result.stdout.splitlines() if t]

    def get_changed_files(self, revspec: str | None) -> list[Path]:
        """List files changed between ``revspec`` and ``HEAD`` as repo paths.

        Args:
            revspec: Two-dot range such as ``tag..HEAD``, or None to diff
                against ``HEAD`` only (working tree vs index/commit as
                implemented by plain ``git diff --name-only HEAD``).
        """
        if revspec:
            result = self._run(["diff", "--name-only", revspec])
        else:
            result = self._run(["diff", "--name-only", "HEAD"])

        return [self.root / f for f in result.stdout.splitlines() if f]

    def has_changes_to_commit(self) -> bool:
        """Return True when tracked or untracked files would be committed."""
        result = self._run(["status", "--porcelain"])

        return bool(result.stdout.strip())

    def commit_all(self, message: str) -> str:
        """Stage all changes, commit with ``message``, return the new hash.

        Args:
            message: Full ``git commit -m`` argument text.
        """
        self._run(["add", "--all"])
        self._run(["commit", "-m", message])

        result = self._run(["rev-parse", "HEAD"])

        return result.stdout.strip()

    def create_tag(self, tag_name: str, message: str | None = None) -> None:
        """Create an annotated or lightweight tag pointing at ``HEAD``.

        Args:
            tag_name: Name of the tag to create.
            message: Optional annotation body; lightweight tag when omitted.
        """
        if message:
            self._run(["tag", "-a", tag_name, "-m", message])
        else:
            self._run(["tag", tag_name])

    def push_branch(self, remote: str, branch: str) -> None:
        """Push ``branch`` to ``remote``."""
        self._run(["push", remote, branch])

    def push_tag(self, remote: str, tag_name: str) -> None:
        """Push a single tag ref to ``remote``."""
        self._run(["push", remote, tag_name])

    def push_tags(self, remote: str, tag_names: Sequence[str]) -> None:
        """Push each tag in ``tag_names`` to ``remote`` sequentially.

        Args:
            remote: Name of the Git remote (for example ``origin``).
            tag_names: Tag refs to publish one ``git push`` at a time.
        """
        for tag_name in tag_names:
            self.push_tag(remote, tag_name)

    def get_current_branch(self) -> str:
        """Return the symbolic branch name for ``HEAD``."""
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])

        return result.stdout.strip()

    def rev_parse(self, ref: str) -> str:
        """Resolve ``ref`` to a full object name.

        Args:
            ref: Any rev-parse accepted reference (branch, tag, SHA prefix).
        """
        result = self._run(["rev-parse", ref])

        return result.stdout.strip()

    def tag_exists(self, tag_name: str) -> bool:
        """Return True when a tag named ``tag_name`` exists locally."""
        result = self._run(["tag", "--list", tag_name], check=False)

        return bool(result.stdout.strip())

    def get_remote_url(self, remote: str = "origin") -> str | None:
        """Return the configured URL for ``remote``, or None when missing.

        Args:
            remote: Local remote name (typically ``origin``).
        """
        result = self._run(["remote", "get-url", remote], check=False)

        if result.returncode != 0:
            log.debug(
                "Could not read URL for remote %r: %s",
                remote,
                result.stderr.strip(),
            )

            return None

        url = result.stdout.strip()

        return url or None

    def list_commits_between(
        self,
        revspec: str | None,
        path: str | None = None,
    ) -> list[GitCommitRecord]:
        """Return commits in oldest-first order for a revision range.

        Args:
            revspec: Two-dot range such as ``tag..HEAD``, or None for full
                history reachable from ``HEAD``.
            path: Optional repository-relative path limiting commits.
        """
        fmt = (
            "%H"
            + _LOG_FIELD_SEP
            + "%h"
            + _LOG_FIELD_SEP
            + "%an"
            + _LOG_FIELD_SEP
            + "%ai"
            + _LOG_FIELD_SEP
            + "%s"
            + _LOG_FIELD_SEP
            + "%b"
            + _LOG_RECORD_SEP
        )

        args: list[str] = ["log"]

        if revspec:
            args.append(revspec)
        else:
            args.append("HEAD")

        args.extend(
            [
                "--reverse",
                f"--pretty=format:{fmt}",
                "--no-merges",
            ]
        )

        if path:
            args.extend(["--", path])

        result = self._run(args)

        return _parse_git_log_output(result.stdout)

    def get_initial_commit_sha(self) -> str | None:
        """Return the hash of the first (root) commit reachable from HEAD.

        Returns:
            Full object name, or None when the history cannot be resolved.
        """
        result = self._run(
            ["rev-list", "--max-parents=0", "HEAD"],
            check=False,
        )

        if result.returncode != 0:
            log.debug(
                "Could not resolve initial commit: %s",
                result.stderr.strip(),
            )

            return None

        line = result.stdout.strip().splitlines()

        return line[0].strip() if line else None


class GitBackendBuiltinPlugin(GitBackendPlugin):
    """Register the subprocess Git backend with the plugin registry."""

    def get_name(self) -> str:
        """Return the stable identifier for this backend."""
        return "builtin-git"

    def get_version(self) -> str:
        """Return a semver-like version string for the built-in backend."""
        return "1.0.0"

    def register(self, registry: PluginRegistry) -> None:
        """Attach this backend to ``registry`` with ``source='builtin'``.

        Args:
            registry: Active plugin registry for the current distlift run.
        """
        registry.register_git_backend_plugin(self, source="builtin")


def _parse_git_log_output(stdout: str) -> list[GitCommitRecord]:
    """Split formatted ``git log`` stdout into structured rows.

    Args:
        stdout: Raw stdout using ``_LOG_FIELD_SEP`` and ``_LOG_RECORD_SEP``.
    """
    if not stdout.strip():
        return []

    rows: list[GitCommitRecord] = []

    for raw_rec in stdout.split(_LOG_RECORD_SEP):
        rec = raw_rec.strip(_RECORD_CHUNK_STRIP_CHARS)

        if not rec:
            continue

        # Limit splits so an empty %b body still yields a sixth field and any
        # accidental separator characters inside the body remain intact.
        parts = rec.split(_LOG_FIELD_SEP, maxsplit=5)

        if len(parts) != 6:
            log.debug(
                "Skipping malformed git log row with %d fields",
                len(parts),
            )

            continue

        rows.append(
            GitCommitRecord(
                sha_full=parts[0],
                sha_short=parts[1],
                author=parts[2],
                authored_iso=parts[3],
                subject=parts[4],
                body=parts[5],
            )
        )

    return rows
