"""Shared pytest fixtures for distlift tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a minimal Git repository in a temporary directory.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """

    # Initialize an empty repository for tests that need real Git commands.
    subprocess.run(
        ["git", "init", str(tmp_path)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Avoid inheriting global GPG signing; commits must stay non-interactive.
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "tag.gpgSign", "false"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Make an initial commit so HEAD exists for diff and tag operations.
    (tmp_path / "README.md").write_text("test\n")
    subprocess.run(
        ["git", "add", "."], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def tmp_python_project(tmp_git_repo: Path) -> Path:
    """Create a Git repo with a minimal pyproject.toml.

    Args:
        tmp_git_repo: Temporary Git repository fixture.
    """

    # Add the Python package manifest used by language adapter tests.
    (tmp_git_repo / "pyproject.toml").write_text(
        '[project]\nname = "mypackage"\nversion = "0.1.0"\n'
    )
    subprocess.run(
        ["git", "add", "."], cwd=tmp_git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add pyproject.toml"],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )
    return tmp_git_repo


@pytest.fixture
def tmp_js_project(tmp_git_repo: Path) -> Path:
    """Create a Git repo with a minimal package.json.

    Args:
        tmp_git_repo: Temporary Git repository fixture.
    """

    # Add the JavaScript package manifest used by language adapter tests.
    (tmp_git_repo / "package.json").write_text(
        '{\n  "name": "mypkg",\n  "version": "1.0.0"\n}\n'
    )
    subprocess.run(
        ["git", "add", "."], cwd=tmp_git_repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add package.json"],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )
    return tmp_git_repo


@pytest.fixture
def monorepo_abc_git_repo(tmp_git_repo: Path) -> Path:
    """Git repo with packages a, b, c where b and c depend on pkg-a.

    Args:
        tmp_git_repo: Initialized temporary Git repository.
    """
    (tmp_git_repo / "packages" / "a").mkdir(parents=True)
    (tmp_git_repo / "packages" / "b").mkdir(parents=True)
    (tmp_git_repo / "packages" / "c").mkdir(parents=True)

    (tmp_git_repo / "packages" / "a" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
    )
    (tmp_git_repo / "packages" / "b" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
        'dependencies = ["pkg-a>=1.0.0"]\n'
    )
    (tmp_git_repo / "packages" / "c" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-c"\nversion = "0.1.0"\n'
        'dependencies = ["pkg-a>=1.0.0"]\n'
    )
    (tmp_git_repo / "distlift.toml").write_text(
        """
[release]
mode = "monorepo"
language = "python"

[dependency_updates]
enabled = true

[[monorepo.packages]]
name = "a"
path = "packages/a"

[[monorepo.packages]]
name = "b"
path = "packages/b"

[[monorepo.packages]]
name = "c"
path = "packages/c"
"""
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add monorepo packages"],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )

    return tmp_git_repo
