"""Tests for external monorepo project loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

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


class TestExternalMonorepoProjects:
    """Tests for external monorepo scanning."""

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

    def test_loads_external_path_outside_repo(self, tmp_path: Path) -> None:
        """Load managed projects from a monorepo outside the release repo."""
        release_root = tmp_path / "release"
        release_root.mkdir()

        outside = tmp_path / "outside"
        (outside / "packages" / "d").mkdir(parents=True)
        (outside / "packages" / "d" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-d"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (outside / "distlift.toml").write_text(
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
            release_root,
            outside,
            [],
            app,
        )

        assert len(projects) == 1
        assert projects[0].name == "d"

    def test_loads_simple_repo_version_files(self, tmp_path: Path) -> None:
        """Load dependency projects from a simple external distlift repo."""
        release_root = tmp_path / "release"
        release_root.mkdir()

        outside = tmp_path / "outside"
        (outside / "backend").mkdir(parents=True)
        (outside / "frontend").mkdir(parents=True)
        (outside / "backend" / "pyproject.toml").write_text(
            '[project]\nname = "app-backend"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (outside / "frontend" / "package.json").write_text(
            "{\n"
            '  "name": "app-frontend",\n'
            '  "version": "0.1.0",\n'
            '  "dependencies": {\n'
            '    "@advtslib/i18n": "^0.1.0"\n'
            "  }\n"
            "}\n"
        )
        (outside / "distlift.toml").write_text(
            """
mode = "simple"
version_source = "manifest"

[[version_files]]
path = "backend/pyproject.toml"
kind = "pyproject"
primary = true

[[version_files]]
path = "frontend/package.json"
kind = "package-json"
"""
        )
        app = DistliftApplication()

        projects = load_external_monorepo_projects(
            release_root,
            outside,
            [],
            app,
        )

        names = {project.name for project in projects}
        manifests = {project.manifest_path.name for project in projects}

        assert names == {"outside/backend", "outside/frontend"}
        assert manifests == {"pyproject.toml", "package.json"}

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
