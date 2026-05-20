"""Tests for JavaScript dependency declaration updates."""

from pathlib import Path

from distlift.dependencies.javascript import update_javascript_dependency


class TestJavascriptDependencyUpdate:
    """Tests for package.json dependency autoupdate."""

    def test_updates_dependencies_group(self, tmp_path: Path) -> None:
        """Replace a matching entry in dependencies."""
        path = tmp_path / "package.json"
        path.write_text(
            '{\n  "name": "b",\n  "version": "0.1.0",\n'
            '  "dependencies": {\n    "a": "^1.0.0"\n  }\n}\n'
        )

        changes = update_javascript_dependency(
            path, "a", "^{version}", "1.2.0", dry_run=False
        )

        assert changes == [("^1.0.0", "^1.2.0")]
        assert '"a": "^1.2.0"' in path.read_text()

    def test_converts_workspace_protocol(self, tmp_path: Path) -> None:
        """Map workspace:* to the configured version template."""
        path = tmp_path / "package.json"
        path.write_text(
            '{\n  "name": "b",\n  "version": "0.1.0",\n'
            '  "dependencies": {\n    "a": "workspace:*"\n  }\n}\n'
        )

        update_javascript_dependency(
            path, "a", "^{version}", "1.2.0", dry_run=False
        )

        assert '"a": "^1.2.0"' in path.read_text()

    def test_updates_dev_dependencies(self, tmp_path: Path) -> None:
        """Update devDependencies entries."""
        path = tmp_path / "package.json"
        path.write_text(
            '{\n  "name": "b",\n  "version": "0.1.0",\n'
            '  "devDependencies": {\n    "a": "1.0.0"\n  }\n}\n'
        )

        update_javascript_dependency(
            path, "a", "^{version}", "2.0.0", dry_run=False
        )

        assert '"a": "^2.0.0"' in path.read_text()

    def test_updates_peer_dependencies(self, tmp_path: Path) -> None:
        """Replace a matching entry in peerDependencies."""
        path = tmp_path / "package.json"
        path.write_text(
            '{\n  "name": "b",\n  "version": "0.1.0",\n'
            '  "peerDependencies": {\n    "a": "^1.0.0"\n  }\n}\n'
        )

        update_javascript_dependency(
            path, "a", "^{version}", "1.2.0", dry_run=False
        )

        assert '"a": "^1.2.0"' in path.read_text()

    def test_updates_optional_dependencies(self, tmp_path: Path) -> None:
        """Replace a matching entry in optionalDependencies."""
        path = tmp_path / "package.json"
        path.write_text(
            '{\n  "name": "b",\n  "version": "0.1.0",\n'
            '  "optionalDependencies": {\n    "a": "1.0.0"\n  }\n}\n'
        )

        update_javascript_dependency(
            path, "a", "^{version}", "3.0.0", dry_run=False
        )

        assert '"a": "^3.0.0"' in path.read_text()
