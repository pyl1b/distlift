"""Tests for distlift dependencies autoupdate CLI."""

import re

from typer.testing import CliRunner

from distlift.cli import app


def _normalize_cli_help(output: str) -> str:
    """Collapse CLI help output for stable substring checks.

    Args:
        output: Raw stdout from a Typer ``CliRunner`` invocation.
    """
    text = re.sub(r"\x1b\[[0-9;]*m", "", output)
    text = re.sub(r"\s+", " ", text)

    # Rich may break long tokens such as ``monorepos`` across wrapped lines.
    return text.replace("mono repos", "monorepos")


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
    """CLI tests for the deps autoupdate command."""

    def test_normalize_cli_help_repairs_wrapped_monorepos(self) -> None:
        """Wrapped help lines must not break monorepo phrase assertions."""
        wrapped = (
            "scan the current monorepo, configured external mono\nrepos, and"
        )
        assert "configured external monorepos" in _normalize_cli_help(wrapped)

    def test_autoupdate_help_explains_scope_and_side_effects(self) -> None:
        """Describe what autoupdate changes and what it deliberately omits."""
        runner = CliRunner()

        result = runner.invoke(app, ["deps", "autoupdate", "--help"])
        help_text = _normalize_cli_help(result.output)

        assert result.exit_code == 0, result.output
        assert "During a distlift release" in help_text
        assert "same dependency-update logic runs automatically" in help_text
        assert "manual shortcut" in help_text
        assert "version was bumped without distlift" in help_text
        assert "release did not update dependents" in help_text
        assert "PACKAGE=VERSION" in help_text
        assert "dependency_updates configuration section" in help_text
        assert "current monorepo" in help_text
        assert "configured external monorepos" in help_text
        assert "does not discover new package versions" in help_text
        assert "create tags, or push to Git" in help_text
        assert "distlift deps upgrade" in help_text
        assert "dependencies_autoupdated hooks" in help_text

    def test_autoupdate_dry_run(self, tmp_path) -> None:
        """Preview dependency updates without writing files."""
        _setup_two_package_repo(tmp_path)
        (tmp_path / "distlift.toml").write_text(_MONOREPO_TOML)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "deps",
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

    def test_autoupdate_short_group_name(self, tmp_path) -> None:
        """The autoupdate command is exposed under the deps group."""
        _setup_two_package_repo(tmp_path)
        (tmp_path / "distlift.toml").write_text(_MONOREPO_TOML)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "deps",
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
                "deps",
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
                "deps",
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
