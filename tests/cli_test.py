import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from distlift import editor as editor_module
from distlift.app import DistliftApplication
from distlift.cli import app
from distlift.config import files as files_module
from distlift.config.files import STUB_CONFIG_CONTENT
from distlift.editor import EDITOR_ENV_VARS
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
        assert "editor" in result.output

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
            skip_changelog_editor: bool = False,
            registry: object | None = None,
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            captured["repo_root"] = repo_root
            captured["dry_run"] = dry_run
            captured["build"] = build
            captured["publish"] = publish
            captured["skip_changelog"] = skip_changelog
            captured["skip_changelog_editor"] = skip_changelog_editor
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
        assert captured.get("skip_changelog_editor") is False
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
            skip_changelog_editor: bool = False,
            registry: object | None = None,
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            captured["build"] = build
            captured["publish"] = publish
            captured["skip_changelog_editor"] = skip_changelog_editor
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
        assert captured.get("skip_changelog_editor") is False

    def test_no_subcommand_forwards_no_changelog_editor(
        self, tmp_python_project: Path, monkeypatch
    ) -> None:
        """``--no-changelog-editor`` reaches ``run_default_command``."""
        captured: dict[str, bool] = {}

        def fake_run_default_command(
            self: DistliftApplication,
            repo_root: Path,
            config: object,
            *,
            dry_run: bool,
            build: bool,
            publish: bool,
            skip_changelog: bool = False,
            skip_changelog_editor: bool = False,
            registry: object | None = None,
        ) -> tuple[ReleaseResult, PublishRunResult | None]:
            captured["skip_changelog_editor"] = skip_changelog_editor
            return ReleaseResult(
                success=True, dry_run=dry_run, tag_names=[]
            ), None

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
                "--no-changelog-editor",
            ],
        )
        assert captured["skip_changelog_editor"] is True

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


class TestConfigInitAndEditCommands:
    """Cover ``config init-user/system`` and ``config edit-user/system``."""

    def _redirect_scopes(
        self, tmp_path: Path, monkeypatch
    ) -> tuple[Path, Path]:
        """Point user and system lookups at temp paths.

        Args:
            tmp_path: Pytest temporary directory used as the scope root.
            monkeypatch: Pytest monkeypatch fixture.
        """
        user_path = tmp_path / "user" / "distlift" / "config.toml"
        system_path = tmp_path / "system" / "distlift" / "config.toml"
        monkeypatch.setattr(
            files_module, "DEFAULT_USER_CONFIG_PATHS", [user_path]
        )
        monkeypatch.setattr(
            files_module, "DEFAULT_SYSTEM_CONFIG_PATHS", [system_path]
        )
        return user_path, system_path

    def _stub_editor(
        self,
        monkeypatch,
        exit_code: int = 0,
        *,
        config_editor: str | None = None,
    ) -> dict[str, Any]:
        """Replace ``subprocess.run`` so no real editor is launched.

        Args:
            monkeypatch: Pytest monkeypatch fixture.
            exit_code: Exit status the fake editor process reports.
            config_editor: Value to return from the merged-config editor
                resolver, isolating tests from the host's real config.
        """
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("EDITOR", "myeditor")

        # Avoid hitting real user/system config files when resolving the
        # configured editor fallback during CLI tests
        monkeypatch.setattr(
            files_module,
            "_resolve_global_editor_command",
            lambda: config_editor,
        )

        captured: dict[str, Any] = {}

        def fake_run(argv, **kwargs):  # noqa: ANN001
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, exit_code)

        monkeypatch.setattr(editor_module.subprocess, "run", fake_run)
        return captured

    def test_init_user_creates_stub(self, tmp_path: Path, monkeypatch) -> None:
        """``config init-user`` writes the stub at the user path."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)

        result = runner.invoke(app, ["config", "init-user"])

        assert result.exit_code == 0
        assert user_path.is_file()
        assert user_path.read_text(encoding="utf-8") == STUB_CONFIG_CONTENT
        assert "Created user config" in result.output

    def test_init_user_keeps_existing_without_force(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Existing user files are preserved without ``--force``."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text("# kept\n", encoding="utf-8")

        result = runner.invoke(app, ["config", "init-user"])

        assert result.exit_code == 0
        assert user_path.read_text(encoding="utf-8") == "# kept\n"
        assert "already exists" in result.output

    def test_init_user_force_overwrites(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``--force`` replaces the file with the default stub."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text("# kept\n", encoding="utf-8")

        result = runner.invoke(app, ["config", "init-user", "--force"])

        assert result.exit_code == 0
        assert user_path.read_text(encoding="utf-8") == STUB_CONFIG_CONTENT

    def test_init_user_unsupported_platform_errors(self, monkeypatch) -> None:
        """Missing OS location yields a clear non-zero exit."""
        monkeypatch.setattr(files_module, "DEFAULT_USER_CONFIG_PATHS", [])

        result = runner.invoke(app, ["config", "init-user"])

        assert result.exit_code == 1
        assert "Cannot determine" in result.output

    def test_init_system_creates_stub(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``config init-system`` writes the stub at the system path."""
        _, system_path = self._redirect_scopes(tmp_path, monkeypatch)

        result = runner.invoke(app, ["config", "init-system"])

        assert result.exit_code == 0
        assert system_path.is_file()
        assert "Created system config" in result.output

    def test_edit_user_creates_then_launches_editor(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A missing file is seeded before the editor is invoked."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)
        captured = self._stub_editor(monkeypatch)

        result = runner.invoke(app, ["config", "edit-user"])

        assert result.exit_code == 0
        assert user_path.is_file()
        assert captured["argv"][-1] == str(user_path)

    def test_edit_user_no_create_errors_when_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``--no-create`` refuses to seed and exits non-zero."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)
        self._stub_editor(monkeypatch)

        result = runner.invoke(app, ["config", "edit-user", "--no-create"])

        assert result.exit_code == 1
        assert not user_path.exists()
        assert "init-user" in result.output

    def test_edit_user_missing_editor_errors(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """No editor env var yields the verbose ``ConfigurationError``."""
        self._redirect_scopes(tmp_path, monkeypatch)
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        # Suppress any ``editor`` value present in the host's real config
        monkeypatch.setattr(
            files_module,
            "_resolve_global_editor_command",
            lambda: None,
        )

        result = runner.invoke(app, ["config", "edit-user"])

        assert result.exit_code == 1
        # The message should reference all three variables for users
        for key in EDITOR_ENV_VARS:
            assert key in result.output

    def test_edit_user_forwards_editor_failure(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A non-zero editor exit propagates to the CLI exit code."""
        self._redirect_scopes(tmp_path, monkeypatch)
        self._stub_editor(monkeypatch, exit_code=7)

        result = runner.invoke(app, ["config", "edit-user"])

        assert result.exit_code == 7
        assert "Editor exited with status 7" in result.output

    def test_edit_system_opens_system_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``config edit-system`` opens the system-scoped file."""
        _, system_path = self._redirect_scopes(tmp_path, monkeypatch)
        captured = self._stub_editor(monkeypatch)

        result = runner.invoke(app, ["config", "edit-system"])

        assert result.exit_code == 0
        assert system_path.is_file()
        assert captured["argv"][-1] == str(system_path)

    def test_edit_user_uses_config_editor_when_env_unset(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The merged ``editor`` setting drives editor choice without env."""
        user_path, _ = self._redirect_scopes(tmp_path, monkeypatch)
        captured = self._stub_editor(
            monkeypatch, config_editor="cfg-editor --wait"
        )

        # Drop the env editor introduced by ``_stub_editor`` to leave the
        # config-supplied fallback as the only available editor source
        monkeypatch.delenv("EDITOR", raising=False)

        result = runner.invoke(app, ["config", "edit-user"])

        assert result.exit_code == 0
        assert captured["argv"][0] == "cfg-editor"
        assert captured["argv"][-1] == str(user_path)
