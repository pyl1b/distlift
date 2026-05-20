"""Integration tests for dependency updates during release execution."""

from __future__ import annotations

import subprocess
from pathlib import Path

from distlift.app import DistliftApplication
from distlift.config.models import (
    BumpKind,
    DependencyUpdatesConfig,
    HooksConfig,
    HookSpec,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.release.models import MonorepoReleaseRequest


def _write_monorepo_with_deps(repo: Path) -> None:
    """Create packages a, b, and c where b and c depend on a.

    Args:
        repo: Repository root path.
    """
    (repo / "packages" / "a").mkdir(parents=True)
    (repo / "packages" / "b").mkdir(parents=True)
    (repo / "packages" / "c").mkdir(parents=True)

    (repo / "packages" / "a" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
    )
    (repo / "packages" / "b" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
        'dependencies = ["pkg-a>=1.0.0"]\n'
    )
    (repo / "packages" / "c" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-c"\nversion = "0.1.0"\n'
        'dependencies = ["pkg-a>=1.0.0"]\n'
    )
    (repo / "distlift.toml").write_text(
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


class TestExecutorDependencyUpdates:
    """Release executor updates dependents before commit."""

    def test_monorepo_release_updates_dependents(
        self, tmp_git_repo: Path
    ) -> None:
        """Releasing a updates b and c dependency declarations before tag."""
        _write_monorepo_with_deps(tmp_git_repo)
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add monorepo"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        app = DistliftApplication()
        config = app.load_effective_config(tmp_git_repo)
        config = ResolvedConfig(
            language=Language.PYTHON,
            mode=ReleaseMode.MONOREPO,
            default_version="0.1.0",
            version_format=VersionFormat.MAJOR_MINOR_PATCH,
            remotes=[],
            tag_template="v{version}-{package}",
            monorepo=MonorepoConfig(
                enabled=True,
                packages=[
                    ManagedPackageConfig(
                        name="a",
                        path="packages/a",
                        language=Language.PYTHON,
                        default_version="1.0.0",
                    ),
                    ManagedPackageConfig(
                        name="b",
                        path="packages/b",
                        language=Language.PYTHON,
                    ),
                    ManagedPackageConfig(
                        name="c",
                        path="packages/c",
                        language=Language.PYTHON,
                    ),
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(enabled=True),
        )

        request = MonorepoReleaseRequest(
            repo_root=tmp_git_repo,
            config=config,
            default_bump=BumpKind.MINOR,
            selected_packages=["a"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        a_text = (
            tmp_git_repo / "packages" / "a" / "pyproject.toml"
        ).read_text()
        b_text = (
            tmp_git_repo / "packages" / "b" / "pyproject.toml"
        ).read_text()
        c_text = (
            tmp_git_repo / "packages" / "c" / "pyproject.toml"
        ).read_text()
        assert 'version = "1.1.0"' in a_text
        assert "pkg-a>=1.1.0" in b_text
        assert "pkg-a>=1.1.0" in c_text
        assert result.dependency_updates

    def test_disabled_globally_skips_updates(self, tmp_git_repo: Path) -> None:
        """When dependency_updates.enabled is false, dependents are unchanged."""
        _write_monorepo_with_deps(tmp_git_repo)
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add monorepo"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        app = DistliftApplication()
        config = ResolvedConfig(
            language=Language.PYTHON,
            mode=ReleaseMode.MONOREPO,
            remotes=[],
            tag_template="v{version}-{package}",
            version_format=VersionFormat.MAJOR_MINOR_PATCH,
            monorepo=MonorepoConfig(
                enabled=True,
                packages=[
                    ManagedPackageConfig(name="a", path="packages/a"),
                    ManagedPackageConfig(name="b", path="packages/b"),
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(enabled=False),
        )

        request = MonorepoReleaseRequest(
            repo_root=tmp_git_repo,
            config=config,
            selected_packages=["a"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        b_text = (
            tmp_git_repo / "packages" / "b" / "pyproject.toml"
        ).read_text()
        assert "pkg-a>=1.0.0" in b_text


def _abc_release_config(
    *,
    dependency_enabled: bool = True,
    packages: list[ManagedPackageConfig] | None = None,
) -> ResolvedConfig:
    """Build ResolvedConfig for the a/b/c monorepo test layout.

    Args:
        dependency_enabled: Global dependency_updates.enabled value.
        packages: Optional package list override.
    """
    if packages is None:
        packages = [
            ManagedPackageConfig(
                name="a",
                path="packages/a",
                language=Language.PYTHON,
                default_version="1.0.0",
            ),
            ManagedPackageConfig(
                name="b",
                path="packages/b",
                language=Language.PYTHON,
                default_version="0.1.0",
            ),
            ManagedPackageConfig(
                name="c",
                path="packages/c",
                language=Language.PYTHON,
                default_version="0.1.0",
            ),
        ]

    return ResolvedConfig(
        language=Language.PYTHON,
        mode=ReleaseMode.MONOREPO,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=[],
        tag_template="v{version}-{package}",
        monorepo=MonorepoConfig(enabled=True, packages=packages),
        dependency_updates=DependencyUpdatesConfig(enabled=dependency_enabled),
    )


class TestExecutorDependencyUpdatesExtended:
    """Additional release integration scenarios from the dependency plan."""

    def test_ab_released_together_updates_b_version_and_dependency(
        self, monorepo_abc_git_repo: Path
    ) -> None:
        """When b is in the release, its manifest gets a new version and dep."""
        app = DistliftApplication()
        config = _abc_release_config()
        request = MonorepoReleaseRequest(
            repo_root=monorepo_abc_git_repo,
            config=config,
            default_bump=BumpKind.MINOR,
            selected_packages=["a", "b"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        b_text = (
            monorepo_abc_git_repo / "packages" / "b" / "pyproject.toml"
        ).read_text()
        assert 'version = "0.2.0"' in b_text
        assert "pkg-a>=1.1.0" in b_text
        assert "v0.2.0-b" in result.tag_names
        assert "v1.1.0-a" in result.tag_names

    def test_b_not_in_release_gets_dep_update_without_b_tag(
        self, monorepo_abc_git_repo: Path
    ) -> None:
        """Updating b's dependency does not create a tag when b is not released."""
        app = DistliftApplication()
        config = _abc_release_config()
        request = MonorepoReleaseRequest(
            repo_root=monorepo_abc_git_repo,
            config=config,
            default_bump=BumpKind.MINOR,
            selected_packages=["a"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        b_text = (
            monorepo_abc_git_repo / "packages" / "b" / "pyproject.toml"
        ).read_text()
        assert "pkg-a>=1.1.0" in b_text
        assert "v1.1.0-a" in result.tag_names
        assert not any("b" in t for t in result.tag_names)

    def test_receive_disabled_leaves_dependent_untouched(
        self, monorepo_abc_git_repo: Path
    ) -> None:
        """When receive is disabled on b, releasing a does not change b."""
        packages = [
            ManagedPackageConfig(
                name="a",
                path="packages/a",
                language=Language.PYTHON,
                default_version="1.0.0",
            ),
            ManagedPackageConfig(
                name="b",
                path="packages/b",
                language=Language.PYTHON,
                dependency_updates_receive_enabled=False,
            ),
            ManagedPackageConfig(
                name="c",
                path="packages/c",
                language=Language.PYTHON,
            ),
        ]
        app = DistliftApplication()
        config = _abc_release_config(packages=packages)
        request = MonorepoReleaseRequest(
            repo_root=monorepo_abc_git_repo,
            config=config,
            default_bump=BumpKind.MINOR,
            selected_packages=["a"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        b_text = (
            monorepo_abc_git_repo / "packages" / "b" / "pyproject.toml"
        ).read_text()
        assert "pkg-a>=1.0.0" in b_text

    def test_hook_runs_before_release_commit(
        self, monorepo_abc_git_repo: Path
    ) -> None:
        """dependencies_autoupdated hook effects are included in release commit."""
        import sys

        marker = monorepo_abc_git_repo / "hook_ran.txt"
        script = (
            f"import pathlib; pathlib.Path({str(marker)!r})"
            ".write_text('ok', encoding='utf-8')"
        )
        base = _abc_release_config()
        config = ResolvedConfig(
            language=base.language,
            mode=base.mode,
            default_version=base.default_version,
            version_format=base.version_format,
            remotes=base.remotes,
            tag_template=base.tag_template,
            monorepo=base.monorepo,
            dependency_updates=base.dependency_updates,
            hooks=HooksConfig(
                dependencies_autoupdated=[
                    HookSpec(argv=[sys.executable, "-c", script]),
                ],
            ),
        )
        app = DistliftApplication()
        request = MonorepoReleaseRequest(
            repo_root=monorepo_abc_git_repo,
            config=config,
            default_bump=BumpKind.MINOR,
            selected_packages=["a"],
            all_changed=False,
            dry_run=False,
        )
        result = app.run_monorepo_release(request)

        assert result.success
        assert marker.exists()
        show = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
            cwd=monorepo_abc_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        names = show.stdout
        assert "hook_ran.txt" in names
        assert "packages/b/pyproject.toml" in names
