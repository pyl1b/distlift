"""Tests for distlift dependencies autoupdate CLI."""

from typer.testing import CliRunner

from distlift.cli import app

_MONOREPO_TOML = """\
mode = "monorepo"

[dependency_updates]
enabled = true
include_current_monorepo = true
python_version_template = ">={version}"

[[monorepo.packages]]
name = "a"
path = "packages/a"
language = "python"

[[monorepo.packages]]
name = "b"
path = "packages/b"
language = "python"
"""

_MONOREPO_TOML_DISABLED = """\
mode = "monorepo"

[dependency_updates]
enabled = false

[[monorepo.packages]]
name = "a"
path = "packages/a"
language = "python"

[[monorepo.packages]]
name = "b"
path = "packages/b"
language = "python"
"""


def _setup_two_package_repo(tmp_path):
    (tmp_path / "packages" / "a").mkdir(parents=True)
    (tmp_path / "packages" / "b").mkdir(parents=True)
    (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
    )
    (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
        '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
        'dependencies = ["pkg-a>=1.0.0"]\n'
    )


class TestCliDependencyAutoupdate:
    """CLI tests for the dependencies autoupdate command."""

    def test_autoupdate_dry_run(self, tmp_path) -> None:
        """Preview dependency updates without writing files."""
        _setup_two_package_repo(tmp_path)
        (tmp_path / "distlift.toml").write_text(_MONOREPO_TOML)

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

        assert result.exit_code == 0, result.output
        assert "would update" in result.output
        assert (
            "pkg-a>=1.0.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )

    def test_autoupdate_writes_files(self, tmp_path) -> None:
        """Apply dependency updates to manifests when not in dry-run mode."""
        _setup_two_package_repo(tmp_path)
        (tmp_path / "distlift.toml").write_text(_MONOREPO_TOML)

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

        assert result.exit_code == 0, result.output
        assert "Autoupdated dependencies" in result.output
        assert (
            "pkg-a>=1.2.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )

    def test_autoupdate_disabled_globally(self, tmp_path) -> None:
        """Skip updates when dependency_updates.enabled is false."""
        _setup_two_package_repo(tmp_path)
        (tmp_path / "distlift.toml").write_text(_MONOREPO_TOML_DISABLED)

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

        assert result.exit_code == 0, result.output
        assert "No dependencies autoupdated" in result.output
        assert (
            "pkg-a>=1.0.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )
