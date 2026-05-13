from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a minimal Git repository in a temporary directory."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
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
    # Make an initial commit so HEAD exists
    (tmp_path / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def tmp_python_project(tmp_git_repo: Path) -> Path:
    """A Git repo with a minimal pyproject.toml."""
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
    """A Git repo with a minimal package.json."""
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
