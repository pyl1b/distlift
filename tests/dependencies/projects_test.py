"""Tests for dependency project identity helpers."""

from pathlib import Path

from distlift.config.models import Language, ManagedPackageConfig
from distlift.dependencies.models import (
    DependencyProject,
    ReleasedProjectVersion,
)
from distlift.dependencies.projects import (
    filter_receive_enabled_dependency_projects,
    filter_trigger_enabled_released_versions,
    normalize_python_dependency_name,
)


class TestNormalizePythonDependencyName:
    """Tests for PEP 503 name normalization."""

    def test_normalizes_separators(self) -> None:
        """Collapse underscores and dots to hyphens."""
        assert (
            normalize_python_dependency_name("My_Package.name")
            == "my-package-name"
        )


class TestPerPackageEnablement:
    """Tests for monorepo per-package autoupdate flags."""

    def test_filter_trigger_enabled(self) -> None:
        """Exclude released versions when trigger is disabled."""
        packages = [
            ManagedPackageConfig(
                name="a",
                path="packages/a",
                dependency_updates_trigger_enabled=False,
            ),
        ]
        released = [
            ReleasedProjectVersion(
                package_name="a",
                dependency_name="a",
                version="1.0.0",
                language=Language.PYTHON,
                root=Path("packages/a"),
                manifest_path=Path("packages/a/pyproject.toml"),
            ),
        ]

        assert (
            filter_trigger_enabled_released_versions(released, packages) == []
        )

    def test_filter_receive_enabled(self) -> None:
        """Exclude dependent projects when receive is disabled."""
        packages = [
            ManagedPackageConfig(
                name="b",
                path="packages/b",
                dependency_updates_receive_enabled=False,
            ),
        ]
        projects = [
            DependencyProject(
                name="b",
                dependency_name="b",
                language=Language.PYTHON,
                root=Path("packages/b"),
                manifest_path=Path("packages/b/pyproject.toml"),
            ),
        ]

        assert (
            filter_receive_enabled_dependency_projects(projects, packages)
            == []
        )
