"""Tests for dependency inventory helpers."""

from __future__ import annotations

from pathlib import Path

from distlift.dependencies.inventory import (
    list_javascript_dependencies,
    list_python_dependencies,
)


class TestListPythonDependencies:
    """Tests for Python manifest inventory."""

    def test_lists_main_and_optional_dependencies(
        self, tmp_path: Path
    ) -> None:
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(
            """
[project]
dependencies = ["requests>=2.0"]
optional-dependencies.dev = ["pytest>=7.0"]
""".strip(),
            encoding="utf-8",
        )
        deps = list_python_dependencies(manifest)
        names = {dep.name for dep in deps}
        assert names == {"requests", "pytest"}


class TestListJavascriptDependencies:
    """Tests for JavaScript manifest inventory."""

    def test_lists_all_dependency_groups(self, tmp_path: Path) -> None:
        manifest = tmp_path / "package.json"
        manifest.write_text(
            """
{
  "dependencies": {"react": "^18.0.0"},
  "devDependencies": {"eslint": "^8.0.0"},
  "peerDependencies": {"react-dom": "^18.0.0"},
  "optionalDependencies": {"fsevents": "^2.0.0"}
}
""".strip(),
            encoding="utf-8",
        )
        deps = list_javascript_dependencies(manifest)
        names = {dep.name for dep in deps}
        assert names == {"react", "eslint", "react-dom", "fsevents"}
