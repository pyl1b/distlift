"""Subprocess-backed Git repository helper and built-in backend plugin."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import attrs

from distlift.errors import GitStateError
from distlift.logging_utils import get_logger
from distlift.plugins.base import GitBackendPlugin
from distlift.plugins.registry import PluginRegistry

log = get_logger(__name__)


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
