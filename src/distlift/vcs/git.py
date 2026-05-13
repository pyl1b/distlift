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
    root: Path

    def _run(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        cmd = ["git", "-C", str(self.root), *args]
        log.log(5, "git %s", " ".join(args))
        result = subprocess.run(
            cmd, check=False, text=True, capture_output=True
        )
        if check and result.returncode != 0:
            raise GitStateError(
                f"git {' '.join(args)} failed (exit {result.returncode}):\n"
                f"{result.stderr.strip()}"
            )
        return result

    def ensure_clean_worktree(self) -> None:
        result = self._run(["status", "--porcelain"])
        if result.stdout.strip():
            raise GitStateError(
                "Working tree is not clean. Commit or stash changes before releasing.\n"
                + result.stdout.strip()
            )

    def get_tags(self) -> list[str]:
        result = self._run(["tag", "--list"])
        return [t for t in result.stdout.splitlines() if t]

    def get_tags_matching(self, pattern: str) -> list[str]:
        result = self._run(["tag", "--list", pattern])
        return [t for t in result.stdout.splitlines() if t]

    def get_changed_files(self, revspec: str | None) -> list[Path]:
        if revspec:
            result = self._run(["diff", "--name-only", revspec])
        else:
            result = self._run(["diff", "--name-only", "HEAD"])
        return [self.root / f for f in result.stdout.splitlines() if f]

    def commit_all(self, message: str) -> str:
        self._run(["add", "--all"])
        self._run(["commit", "-m", message])
        result = self._run(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def create_tag(self, tag_name: str, message: str | None = None) -> None:
        if message:
            self._run(["tag", "-a", tag_name, "-m", message])
        else:
            self._run(["tag", tag_name])

    def push_branch(self, remote: str, branch: str) -> None:
        self._run(["push", remote, branch])

    def push_tag(self, remote: str, tag_name: str) -> None:
        self._run(["push", remote, tag_name])

    def push_tags(self, remote: str, tag_names: Sequence[str]) -> None:
        for tag_name in tag_names:
            self.push_tag(remote, tag_name)

    def get_current_branch(self) -> str:
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def rev_parse(self, ref: str) -> str:
        result = self._run(["rev-parse", ref])
        return result.stdout.strip()

    def tag_exists(self, tag_name: str) -> bool:
        result = self._run(["tag", "--list", tag_name], check=False)
        return bool(result.stdout.strip())


class GitBackendBuiltinPlugin(GitBackendPlugin):
    def get_name(self) -> str:
        return "builtin-git"

    def get_version(self) -> str:
        return "1.0.0"

    def register(self, registry: PluginRegistry) -> None:
        registry.register_git_backend_plugin(self, source="builtin")
