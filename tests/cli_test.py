from pathlib import Path

from typer.testing import CliRunner

from distlift.app import DistliftApplication
from distlift.cli import app
from distlift.publish.models import PublishRunResult
from distlift.release.models import ReleaseResult

runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "distlift" in result.output.lower()

    def test_release_simple_no_selector_fails(self):
        result = runner.invoke(app, ["release", "simple"])
        assert result.exit_code != 0

    def test_release_simple_two_selectors_fails(self):
        result = runner.invoke(
            app, ["release", "simple", "--major", "--minor"]
        )
        assert result.exit_code != 0

    def test_config_show_runs(self, tmp_path):
        result = runner.invoke(
            app, ["config", "show", "--repo-root", str(tmp_path)]
        )
        assert result.exit_code == 0

    def test_plugins_list_runs(self, tmp_path):
        result = runner.invoke(
            app, ["plugins", "list", "--repo-root", str(tmp_path)]
        )
        assert result.exit_code == 0

    def test_no_subcommand_invokes_default_release(
        self, tmp_python_project: Path, monkeypatch
    ) -> None:
        """Bare ``distlift`` invokes the patch release workflow."""
        captured: dict[str, object] = {}

        def fake_run_default_command(
            self: DistliftApplication,
            repo_root: Path,
            config: object,
            *,
            dry_run: bool,
            build: bool,
            publish: bool,
            skip_changelog: bool = False,
            registry: object | None = None,
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            captured["repo_root"] = repo_root
            captured["dry_run"] = dry_run
            captured["build"] = build
            captured["publish"] = publish
            captured["skip_changelog"] = skip_changelog
            return (
                ReleaseResult(
                    success=True,
                    dry_run=dry_run,
                    tag_names=["v0.2.2"],
                    commit_sha="abc",
                    pushed_remotes=["origin"],
                ),
                None,
            )

        monkeypatch.setattr(
            DistliftApplication,
            "run_default_command",
            fake_run_default_command,
        )
        result = runner.invoke(app, ["--repo-root", str(tmp_python_project)])
        assert result.exit_code == 0
        assert captured.get("dry_run") is False
        assert captured.get("build") is False
        assert captured.get("publish") is False
        assert captured.get("skip_changelog") is False
        assert captured["repo_root"] == tmp_python_project.resolve()
        assert "v0.2.2" in result.output

    def test_no_subcommand_forwards_build_and_publish_flags(
        self, tmp_python_project: Path, monkeypatch
    ) -> None:
        captured: dict[str, bool | None] = {}

        def fake_run_default_command(
            self: DistliftApplication,
            repo_root: Path,
            config: object,
            *,
            dry_run: bool,
            build: bool,
            publish: bool,
            skip_changelog: bool = False,
            registry: object | None = None,
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            captured["build"] = build
            captured["publish"] = publish
            return (
                ReleaseResult(
                    success=True,
                    dry_run=dry_run,
                    tag_names=["v1"],
                ),
                None,
            )

        monkeypatch.setattr(
            DistliftApplication,
            "run_default_command",
            fake_run_default_command,
        )
        runner.invoke(
            app,
            [
                "--repo-root",
                str(tmp_python_project),
                "--build",
                "--publish",
            ],
        )
        assert captured["build"] is True
        assert captured["publish"] is True

    def test_changelog_preview_runs(self, tmp_python_project: Path) -> None:
        """``distlift changelog preview`` prints a proposed release section."""

        result = runner.invoke(
            app,
            [
                "changelog",
                "preview",
                "--repo-root",
                str(tmp_python_project),
                "--version",
                "0.2.0",
            ],
        )

        assert result.exit_code == 0
        assert "## [" in result.output

    def test_explicit_subcommand_skips_default_command(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        called: list[int] = []

        def fake_run_default_command(
            self: DistliftApplication, *args, **kwargs
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            called.append(1)
            return ReleaseResult(success=True, dry_run=False), None

        monkeypatch.setattr(
            DistliftApplication,
            "run_default_command",
            fake_run_default_command,
        )
        runner.invoke(app, ["config", "show", "--repo-root", str(tmp_path)])
        assert called == []

    def test_default_release_failure_exits_nonzero(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        def fake_run_default_command(
            self: DistliftApplication, *args, **kwargs
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            return (
                ReleaseResult(
                    success=False,
                    dry_run=False,
                    error="no tag",
                ),
                None,
            )

        monkeypatch.setattr(
            DistliftApplication,
            "run_default_command",
            fake_run_default_command,
        )
        result = runner.invoke(app, ["--repo-root", str(tmp_path)])
        assert result.exit_code != 0
