"""Tests for dependency autoupdate data models."""

from pathlib import Path

from distlift.config.models import Language
from distlift.dependencies.models import (
    DependencyUpdateChange,
    DependencyUpdateResult,
    ReleasedProjectVersion,
)


class TestDependencyModels:
    """Tests for attrs models in dependencies.models."""

    def test_released_project_version_fields(self) -> None:
        """Store released package identity and version metadata."""
        root = Path("/repo/packages/a")
        rv = ReleasedProjectVersion(
            package_name="a",
            dependency_name="pkg-a",
            version="1.2.0",
            language=Language.PYTHON,
            root=root,
            manifest_path=root / "pyproject.toml",
        )

        assert rv.package_name == "a"
        assert rv.dependency_name == "pkg-a"
        assert rv.version == "1.2.0"

    def test_dependency_update_result_defaults(self) -> None:
        """Default empty change and warning lists on results."""
        result = DependencyUpdateResult(updater_name="builtin")

        assert result.changes == []
        assert result.warnings == []

    def test_dependency_update_change_is_frozen(self) -> None:
        """DependencyUpdateChange instances are immutable."""
        change = DependencyUpdateChange(
            project_name="b",
            dependency_name="pkg-a",
            manifest_path=Path("b/pyproject.toml"),
            old_specifier=">=1.0.0",
            new_specifier=">=1.2.0",
        )

        assert change.new_specifier == ">=1.2.0"
