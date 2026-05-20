"""Tests for external monorepo project loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from distlift.app import DistliftApplication
from distlift.config.models import (
    DependencyUpdatesConfig,
    ExternalMonorepoDependencyUpdateConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.dependencies.models import (
    DependencyUpdateRequest,
    ReleasedProjectVersion,
)
from distlift.dependencies.projects import load_external_monorepo_projects
from distlift.dependencies.service import run_builtin_dependency_updates
from distlift.errors import ConfigurationError


class TestExternalMonorepoProjects:
    """Tests for in-repo external monorepo scanning."""

    def test_load_external_monorepo_projects(self, tmp_git_repo: Path) -> None:
        """Load managed projects from a nested monorepo inside the release repo."""
        (tmp_git_repo / "packages" / "a").mkdir(parents=True)
        (tmp_git_repo / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        ext = tmp_git_repo / "nested"
        (ext / "packages" / "d").mkdir(parents=True)
        (ext / "packages" / "d" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-d"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (ext / "distlift.toml").write_text(
            """
[release]
mode = "monorepo"
language = "python"

[[monorepo.packages]]
name = "d"
path = "packages/d"
"""
        )
        app = DistliftApplication()
        projects = load_external_monorepo_projects(
            tmp_git_repo,
            ext,
            [],
            app,
        )

        assert len(projects) == 1
        assert projects[0].name == "d"

    def test_rejects_external_path_outside_repo(self, tmp_path: Path) -> None:
        """Raise ConfigurationError when the external root is outside the repo."""
        outside = tmp_path / "outside"
        outside.mkdir()
        app = DistliftApplication()

        with pytest.raises(ConfigurationError, match="outside the release"):
            load_external_monorepo_projects(
                tmp_path / "repo",
                outside,
                [],
                app,
            )

    def test_release_updates_external_monorepo_dependent(
        self, tmp_git_repo: Path
    ) -> None:
        """Update dependencies in a nested monorepo configured as external."""
        (tmp_git_repo / "packages" / "a").mkdir(parents=True)
        (tmp_git_repo / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        ext = tmp_git_repo / "nested"
        (ext / "packages" / "d").mkdir(parents=True)
        (ext / "packages" / "d" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-d"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (ext / "distlift.toml").write_text(
            """
[release]
mode = "monorepo"
language = "python"

[[monorepo.packages]]
name = "d"
path = "packages/d"
"""
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add nested monorepo"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        config = ResolvedConfig(
            language=Language.PYTHON,
            mode=ReleaseMode.MONOREPO,
            remotes=[],
            monorepo=MonorepoConfig(
                enabled=True,
                packages=[
                    ManagedPackageConfig(
                        name="a",
                        path="packages/a",
                        language=Language.PYTHON,
                    ),
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(
                enabled=True,
                include_current_monorepo=False,
                external_monorepos=[
                    ExternalMonorepoDependencyUpdateConfig(
                        path="nested",
                        projects=["*"],
                    ),
                ],
            ),
        )
        request = DependencyUpdateRequest(
            repo_root=tmp_git_repo,
            config=config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=tmp_git_repo / "packages" / "a",
                    manifest_path=tmp_git_repo
                    / "packages"
                    / "a"
                    / "pyproject.toml",
                ),
            ],
            dry_run=False,
        )
        result = run_builtin_dependency_updates(request)

        assert result.changes
        assert (
            "pkg-a>=1.2.0"
            in (ext / "packages" / "d" / "pyproject.toml").read_text()
        )
