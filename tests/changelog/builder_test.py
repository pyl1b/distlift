"""Tests for changelog release planning."""

import subprocess
from datetime import date
from pathlib import Path

from distlift.changelog.builder import build_changelog_update_plan
from distlift.config.models import ChangelogConfig
from distlift.vcs.git import GitRepository


def test_builder_collects_conventional_commits(tmp_git_repo: Path) -> None:
    """Group commits into changelog sections using conventional rules."""
    repo_root = tmp_git_repo

    (repo_root / "a.txt").write_text("a")

    subprocess.run(
        ["git", "add", "a.txt"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "commit", "-m", "feat: add widget", "-m", ""],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    (repo_root / "b.txt").write_text("b")

    subprocess.run(
        ["git", "add", "b.txt"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "commit", "-m", "fix: squish bug", "-m", ""],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "tag", "v0.1.0"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    (repo_root / "c.txt").write_text("c")

    subprocess.run(
        ["git", "add", "c.txt"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "commit", "-m", "feat: later feature", "-m", ""],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    git = GitRepository(root=repo_root)

    cfg = ChangelogConfig(enabled=True, include_unreleased_section=True)

    path = repo_root / "CHANGELOG.md"

    plan = build_changelog_update_plan(
        git,
        path,
        None,
        "v0.1.0",
        "0.2.0",
        "v0.2.0",
        date(2020, 1, 2),
        cfg,
    )

    titles = [sec.title for sec in plan.inserted_release.sections]

    assert "Added" in titles

    added = next(
        s for s in plan.inserted_release.sections if s.title == "Added"
    )

    assert any("later feature" in b for b in added.bullets)
