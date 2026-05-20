"""Tests for built-in dependency autoupdate service."""

from pathlib import Path

from distlift.config.models import (
    DependencyUpdatesConfig,
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
from distlift.dependencies.service import run_builtin_dependency_updates
from distlift.plugins.manager import PluginLoadRequest, PluginManager


def _monorepo_config(
    *,
    enabled: bool = True,
    packages: list[ManagedPackageConfig] | None = None,
) -> ResolvedConfig:
    """Build a monorepo ResolvedConfig for service tests.

    Args:
        enabled: Global dependency_updates.enabled flag.
        packages: Optional package list; defaults to a and b.
    """
    if packages is None:
        packages = [
            ManagedPackageConfig(
                name="a",
                path="packages/a",
                language=Language.PYTHON,
            ),
            ManagedPackageConfig(
                name="b",
                path="packages/b",
                language=Language.PYTHON,
            ),
        ]

    return ResolvedConfig(
        language=Language.PYTHON,
        mode=ReleaseMode.MONOREPO,
        remotes=[],
        monorepo=MonorepoConfig(enabled=True, packages=packages),
        dependency_updates=DependencyUpdatesConfig(enabled=enabled),
    )


class TestRunBuiltinDependencyUpdates:
    """Tests for run_builtin_dependency_updates."""

    def test_disabled_globally_returns_no_changes(
        self, tmp_path: Path
    ) -> None:
        """Skip all work when dependency_updates.enabled is false."""
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        config = _monorepo_config(enabled=False)
        request = DependencyUpdateRequest(
            repo_root=tmp_path,
            config=config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=tmp_path / "packages" / "a",
                    manifest_path=tmp_path
                    / "packages"
                    / "a"
                    / "pyproject.toml",
                ),
            ],
            dry_run=False,
        )

        result = run_builtin_dependency_updates(request)

        assert result.changes == []

    def test_simple_mode_skips_per_package_filters(
        self, tmp_path: Path
    ) -> None:
        """Simple mode does not apply monorepo per-package enablement filters."""
        from unittest.mock import patch

        config = ResolvedConfig(
            language=Language.PYTHON,
            mode=ReleaseMode.SIMPLE,
            remotes=[],
            dependency_updates=DependencyUpdatesConfig(enabled=True),
        )
        request = DependencyUpdateRequest(
            repo_root=tmp_path,
            config=config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=tmp_path / "packages" / "a",
                    manifest_path=tmp_path
                    / "packages"
                    / "a"
                    / "pyproject.toml",
                ),
            ],
            dry_run=True,
        )

        with (
            patch(
                "distlift.dependencies.service.filter_trigger_enabled_released_versions"
            ) as mock_trigger,
            patch(
                "distlift.dependencies.service.filter_receive_enabled_dependency_projects"
            ) as mock_receive,
        ):
            run_builtin_dependency_updates(request)

        mock_trigger.assert_not_called()
        mock_receive.assert_not_called()

    def test_trigger_disabled_skips_released_package(
        self, tmp_path: Path
    ) -> None:
        """Do not propagate updates when the released package cannot trigger."""
        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        config = _monorepo_config(
            packages=[
                ManagedPackageConfig(
                    name="a",
                    path="packages/a",
                    language=Language.PYTHON,
                    dependency_updates_trigger_enabled=False,
                ),
                ManagedPackageConfig(
                    name="b",
                    path="packages/b",
                    language=Language.PYTHON,
                ),
            ],
        )
        request = DependencyUpdateRequest(
            repo_root=tmp_path,
            config=config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=tmp_path / "packages" / "a",
                    manifest_path=tmp_path
                    / "packages"
                    / "a"
                    / "pyproject.toml",
                ),
            ],
            dry_run=True,
        )
        manager = PluginManager()
        registry = manager.build_registry(
            PluginLoadRequest(disable_environment_plugins=True)
        )

        from distlift.dependencies.service import run_dependency_updates

        results = run_dependency_updates(request, registry)

        assert results == []
