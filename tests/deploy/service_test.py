"""Tests for ``distlift deploy`` orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import attrs
import pytest

from distlift.app import DistliftApplication
from distlift.config.models import (
    ChangelogConfig,
    DeployConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.config.validators import validate_resolved_config
from distlift.deploy.models import DeployRequest
from distlift.deploy.service import run_deploy
from distlift.vcs.git import GitRepository


def _simple_python_config(**kwargs: object) -> ResolvedConfig:
    """Return a valid simple-mode config for deploy tests.

    Args:
        kwargs: Overrides for ``ResolvedConfig`` fields.
    """
    base: dict[str, object] = dict(
        language=Language.PYTHON,
        mode=ReleaseMode.SIMPLE,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        changelog=attrs.evolve(ChangelogConfig(), enabled=False),
    )
    base.update(kwargs)
    cfg = ResolvedConfig(**base)
    validate_resolved_config(cfg)
    return cfg


def _monorepo_config() -> ResolvedConfig:
    """Two-package monorepo config with changelog off.

    Returns:
        Valid monorepo ``ResolvedConfig``.
    """
    packages = [
        ManagedPackageConfig(
            name="pkg_a",
            path="pkg_a",
            language=Language.PYTHON,
            tag_template="v{version}-{package}",
        ),
        ManagedPackageConfig(
            name="pkg_b",
            path="pkg_b",
            language=Language.PYTHON,
            tag_template="v{version}-{package}",
        ),
    ]

    cfg = ResolvedConfig(
        language=Language.PYTHON,
        mode=ReleaseMode.MONOREPO,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        monorepo=MonorepoConfig(enabled=True, packages=packages),
        changelog=attrs.evolve(ChangelogConfig(), enabled=False),
    )
    validate_resolved_config(cfg)
    return cfg


class TestRunDeploy:
    """Tests for :func:`~distlift.deploy.service.run_deploy`."""

    def test_dry_run_does_not_create_tag(
        self,
        tmp_python_project: Path,
    ) -> None:
        """Dry-run reports the planned tag name without creating it."""

        cfg = _simple_python_config()
        result = run_deploy(
            DeployRequest(
                repo_root=tmp_python_project,
                config=cfg,
                dry_run=True,
            ),
        )

        assert result.success is True
        assert result.dry_run is True
        assert result.tag_name == "deploy_1"

        tags_out = subprocess.run(
            ["git", "tag", "--list"],
            cwd=tmp_python_project,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "deploy_1" not in tags_out.stdout.splitlines()

    def test_dirty_worktree_fails(
        self,
        tmp_python_project: Path,
    ) -> None:
        """Unclean worktree yields a failed result."""

        dirty = tmp_python_project / "dirty.txt"
        dirty.write_text("x", encoding="utf-8")

        cfg = _simple_python_config()
        result = run_deploy(
            DeployRequest(repo_root=tmp_python_project, config=cfg),
        )

        assert result.success is False
        assert result.error is not None
        assert "not clean" in result.error.lower()

    def test_creates_and_pushes_tag(
        self,
        tmp_python_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Successful run creates an annotated tag and pushes per remote."""

        cfg = _simple_python_config()
        pushes: list[tuple[str, str]] = []

        def push_tag(self: GitRepository, remote: str, tag_name: str) -> None:
            pushes.append((remote, tag_name))

        monkeypatch.setattr(GitRepository, "push_tag", push_tag)

        result = run_deploy(
            DeployRequest(repo_root=tmp_python_project, config=cfg),
        )

        assert result.success is True
        assert result.tag_name == "deploy_1"
        assert pushes == [("origin", "deploy_1")]

        tags_out = subprocess.run(
            ["git", "tag", "--list", "deploy_1"],
            cwd=tmp_python_project,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "deploy_1" in tags_out.stdout

    def test_respects_deploy_tag_prefix_config(
        self,
        tmp_python_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``deploy.tag_prefix`` names the generated tag."""

        cfg = _simple_python_config(
            deploy=DeployConfig(tag_prefix="rel", verify_indexes=False)
        )

        monkeypatch.setattr(
            GitRepository,
            "push_tag",
            lambda *_a: None,
        )

        result = run_deploy(
            DeployRequest(repo_root=tmp_python_project, config=cfg),
        )

        assert result.success is True
        assert result.tag_name == "rel_1"

    def test_verify_indexes_failure_skips_tag(
        self,
        tmp_python_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When verification fails, no tag is created."""

        cfg = _simple_python_config(
            deploy=DeployConfig(verify_indexes=True),
        )

        check = MagicMock()
        check.ok = False
        check.label = "x"
        check.registry_name = "y"
        check.detail = "missing"

        monkeypatch.setattr(
            "distlift.deploy.service._verify_targets",
            lambda _targets: [check],
        )
        monkeypatch.setattr(
            GitRepository,
            "push_tag",
            lambda *_a: None,
        )

        result = run_deploy(
            DeployRequest(repo_root=tmp_python_project, config=cfg),
        )

        assert result.success is False

        tags_out = subprocess.run(
            ["git", "tag", "--list"],
            cwd=tmp_python_project,
            capture_output=True,
            text=True,
            check=True,
        )
        assert not any(
            t.startswith("deploy_") for t in tags_out.stdout.splitlines()
        )

    def test_app_run_deploy_delegates(
        self,
        tmp_python_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """:meth:`DistliftApplication.run_deploy` returns a deploy result."""

        monkeypatch.setattr(
            GitRepository,
            "push_tag",
            lambda *_a: None,
        )

        cfg = _simple_python_config()
        app = DistliftApplication()
        result = app.run_deploy(
            DeployRequest(
                repo_root=tmp_python_project,
                config=cfg,
                dry_run=True,
            )
        )

        assert result.success is True
        assert result.tag_name == "deploy_1"


def _two_package_repo(repo: Path) -> None:
    """Add two Python packages and commit.

    Args:
        repo: Git repository root.
    """
    (repo / "pkg_a").mkdir()
    (repo / "pkg_a" / "pyproject.toml").write_text(
        '[project]\nname = "pkg_a"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (repo / "pkg_b").mkdir()
    (repo / "pkg_b" / "pyproject.toml").write_text(
        '[project]\nname = "pkg_b"\nversion = "2.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add packages"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class TestRunDeployMonorepo:
    """Deploy behavior in monorepo mode."""

    def test_dry_run_with_verify_runs_checks(
        self,
        tmp_git_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Monorepo with ``verify_indexes`` still produces one deploy tag."""

        _two_package_repo(tmp_git_repo)
        cfg = _monorepo_config()

        monkeypatch.setattr(
            "distlift.deploy.service._verify_targets",
            lambda _targets: [],
        )

        cfg_verify = attrs.evolve(
            cfg,
            deploy=DeployConfig(verify_indexes=True),
        )

        result = run_deploy(
            DeployRequest(
                repo_root=tmp_git_repo,
                config=cfg_verify,
                dry_run=True,
            ),
        )

        assert result.success is True
        assert result.tag_name == "deploy_1"
