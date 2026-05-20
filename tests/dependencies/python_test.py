"""Tests for Python dependency declaration updates."""

from pathlib import Path

from distlift.dependencies.python import (
    find_python_dependency_specs,
    update_python_dependency,
)


class TestPythonDependencyUpdate:
    """Tests for pyproject.toml dependency autoupdate."""

    def test_updates_project_dependencies(self, tmp_path: Path) -> None:
        """Replace a matching requirement in [project].dependencies."""
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[project]\nname = "b"\nversion = "0.1.0"\n'
            'dependencies = ["a>=1.0"]\n'
        )

        changes = update_python_dependency(
            path, "a", ">={version}", "1.2.0", dry_run=False
        )

        assert changes == [("a>=1.0", "a>=1.2.0")]
        assert "a>=1.2.0" in path.read_text()

    def test_preserves_extras_and_markers(self, tmp_path: Path) -> None:
        """Keep extras and environment markers when updating a requirement."""
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[project]\nname = "b"\nversion = "0.1.0"\n'
            "dependencies = [\n"
            '  "a[cli]>=1.0; python_version >= \\"3.11\\"",\n'
            "]\n"
        )

        update_python_dependency(
            path, "a", ">={version}", "1.2.0", dry_run=False
        )

        text = path.read_text()
        assert "a[cli]>=1.2.0" in text
        assert "python_version" in text

    def test_updates_optional_dependencies(self, tmp_path: Path) -> None:
        """Update a dependency inside [project.optional-dependencies]."""
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[project]\nname = "b"\nversion = "0.1.0"\n'
            "[project.optional-dependencies]\n"
            'dev = ["a>=1.0"]\n'
        )

        specs = find_python_dependency_specs(path, "a")

        assert len(specs) == 1
        assert specs[0].section == "dev"

        update_python_dependency(
            path, "a", ">={version}", "2.0.0", dry_run=False
        )

        assert "a>=2.0.0" in path.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """Report changes without modifying the file when dry_run is True."""
        path = tmp_path / "pyproject.toml"
        original = (
            '[project]\nname = "b"\nversion = "0.1.0"\n'
            'dependencies = ["a>=1.0"]\n'
        )
        path.write_text(original)

        changes = update_python_dependency(
            path, "a", ">={version}", "1.2.0", dry_run=True
        )

        assert changes == [("a>=1.0", "a>=1.2.0")]
        assert path.read_text() == original
