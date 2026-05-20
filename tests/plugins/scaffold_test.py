"""Tests for plugin scaffolding helpers."""

from pathlib import Path

from distlift.config.models import DependencyUpdateRule
from distlift.plugins.scaffold import (
    DependencyUpdaterTemplateOptions,
    create_dependency_updater_plugin,
)


class TestScaffoldDependencyUpdater:
    """Tests for create_dependency_updater_plugin."""

    def test_creates_plugin_files(self, tmp_path: Path) -> None:
        """Write plugin project files under the output directory."""
        options = DependencyUpdaterTemplateOptions(
            name="my-updater",
            output_dir=tmp_path / "plugin",
            rules=[DependencyUpdateRule(package="a", projects=["b"])],
            external_monorepos=[],
        )

        written = create_dependency_updater_plugin(options)

        assert (tmp_path / "plugin" / "pyproject.toml").exists()
        assert any(p.name == "plugin.py" for p in written)
        assert (tmp_path / "plugin" / "my_updater" / "__init__.py").exists()
