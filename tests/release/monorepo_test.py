"""Tests for monorepo release planning."""

from __future__ import annotations

import subprocess
from pathlib import Path

import attrs

from distlift.app import DistliftApplication
from distlift.config.models import (
    ChangelogConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.config.validators import validate_resolved_config
from distlift.release.models import MonorepoReleaseRequest
from distlift.release.monorepo import compute_monorepo_release_plan
from distlift.versioning.formatter import format_version


def _two_package_repo(tmp_git_repo: Path) -> None:
    """Add two Python packages and commit (clean worktree).

    Args:
        tmp_git_repo: Initialized Git repository root.
    """
    (tmp_git_repo / "pkg_a").mkdir()
    (tmp_git_repo / "pkg_a" / "pyproject.toml").write_text(
        '[project]\nname = "pkg_a"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (tmp_git_repo / "pkg_b").mkdir()
    (tmp_git_repo / "pkg_b" / "pyproject.toml").write_text(
        '[project]\nname = "pkg_b"\nversion = "2.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add packages"],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )


def _monorepo_config() -> ResolvedConfig:
    """Build a valid monorepo ``ResolvedConfig`` with changelog disabled.

    Returns:
        Configuration validated for two managed Python packages.
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


class TestMonorepoReleasePlan:
    """Tests for ``compute_monorepo_release_plan``."""

    def test_explicit_version_unifies_next_version(
        self, tmp_git_repo: Path
    ) -> None:
        """``explicit_version`` produces the same next version per package."""

        _two_package_repo(tmp_git_repo)
        config = _monorepo_config()
        registry = DistliftApplication()._default_registry(config)

        request = MonorepoReleaseRequest(
            repo_root=tmp_git_repo,
            config=config,
            explicit_version="3.0.0",
            selected_packages=[],
            all_changed=False,
            dry_run=True,
            skip_changelog=True,
        )
        plan = compute_monorepo_release_plan(request, registry)

        assert len(plan.packages) == 2
        for pkg_plan in plan.packages:
            assert format_version(pkg_plan.resolved_version.next) == "3.0.0"
            assert "3.0.0" in pkg_plan.resolved_version.tag_name
