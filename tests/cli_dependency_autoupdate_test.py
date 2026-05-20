"""Tests for distlift dependencies autoupdate CLI."""

from typer.testing import CliRunner

from distlift.cli import app


class TestCliDependencyAutoupdate:
    """CLI tests for the dependencies autoupdate command."""

    def test_autoupdate_dry_run(self, tmp_path) -> None:
        """Preview dependency updates without writing files."""
        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (tmp_path / "distlift.toml").write_text(
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
"""
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "dependencies",
                "autoupdate",
                "--released",
                "a=1.2.0",
                "--repo-root",
                str(tmp_path),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "would update" in result.output
        assert (
            "pkg-a>=1.0.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )

    def test_autoupdate_writes_files(self, tmp_path) -> None:
        """Apply dependency updates to manifests when not in dry-run mode."""
        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (tmp_path / "distlift.toml").write_text(
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
"""
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "dependencies",
                "autoupdate",
                "--released",
                "a=1.2.0",
                "--repo-root",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        assert "Autoupdated dependencies" in result.output
        assert (
            "pkg-a>=1.2.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )

    def test_autoupdate_disabled_globally(self, tmp_path) -> None:
        """Skip updates when dependency_updates.enabled is false."""
        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (tmp_path / "distlift.toml").write_text(
            """
[release]
mode = "monorepo"
language = "python"

[dependency_updates]
enabled = false

[[monorepo.packages]]
name = "a"
path = "packages/a"

[[monorepo.packages]]
name = "b"
path = "packages/b"
"""
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "dependencies",
                "autoupdate",
                "--released",
                "a=1.2.0",
                "--repo-root",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        assert "No dependencies autoupdated" in result.output
        assert (
            "pkg-a>=1.0.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )
