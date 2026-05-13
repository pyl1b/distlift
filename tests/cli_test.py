from pathlib import Path

from typer.testing import CliRunner

from distlift.app import DistliftApplication
from distlift.cli import app
from distlift.publish.models import PublishResult, PublishRunResult

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

    def test_no_subcommand_triggers_publish(
        self, tmp_python_project: Path, monkeypatch
    ) -> None:
        """Bare ``distlift`` invokes the default publish path."""
        captured: dict[str, object] = {}

        def fake_run_publish(
            self: DistliftApplication,
            repo_root: Path,
            config: object,
            dry_run: bool,
            registry: object | None = None,
        ) -> PublishRunResult:
            captured["repo_root"] = repo_root
            captured["dry_run"] = dry_run
            return PublishRunResult(
                success=True,
                projects=[
                    ("mypackage", PublishResult(success=True, artifacts=[])),
                ],
            )

        monkeypatch.setattr(
            DistliftApplication, "run_publish", fake_run_publish
        )
        result = runner.invoke(app, ["--repo-root", str(tmp_python_project)])
        assert result.exit_code == 0
        assert captured.get("dry_run") is False
        assert captured["repo_root"] == tmp_python_project.resolve()
        assert "mypackage" in result.output

    def test_explicit_subcommand_skips_default_publish(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        published: list[int] = []

        def fake_run_publish(self: DistliftApplication, *args, **kwargs):
            published.append(1)
            return PublishRunResult(success=True)

        monkeypatch.setattr(
            DistliftApplication, "run_publish", fake_run_publish
        )
        runner.invoke(app, ["config", "show", "--repo-root", str(tmp_path)])
        assert published == []

    def test_publish_mock_failure_exits_nonzero(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        def fake_run_publish(self: DistliftApplication, *args, **kwargs):
            return PublishRunResult(success=False, error="no project")

        monkeypatch.setattr(
            DistliftApplication, "run_publish", fake_run_publish
        )
        result = runner.invoke(app, ["--repo-root", str(tmp_path)])
        assert result.exit_code != 0
