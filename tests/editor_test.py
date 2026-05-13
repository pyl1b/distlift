"""Tests for the shared external-editor utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from distlift import editor
from distlift.editor import (
    EDITOR_ENV_VARS,
    format_missing_editor_message,
    launch_editor_blocking,
    resolve_editor_command,
)
from distlift.errors import ConfigurationError


class TestResolveEditorCommand:
    """Cover priority order and empty-value handling."""

    def test_returns_none_when_all_unset(self, monkeypatch) -> None:
        """Returns ``None`` when none of the supported env vars are set."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        assert resolve_editor_command() is None

    def test_returns_none_when_all_blank(self, monkeypatch) -> None:
        """Blank or whitespace-only values are treated as unset."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.setenv(key, "   ")

        assert resolve_editor_command() is None

    def test_prefers_git_editor(self, monkeypatch) -> None:
        """``GIT_EDITOR`` wins over ``VISUAL`` and ``EDITOR``."""
        monkeypatch.setenv("GIT_EDITOR", "code --wait")
        monkeypatch.setenv("VISUAL", "vim")
        monkeypatch.setenv("EDITOR", "nano")

        assert resolve_editor_command() == "code --wait"

    def test_falls_back_to_visual(self, monkeypatch) -> None:
        """When ``GIT_EDITOR`` is unset, ``VISUAL`` is consulted next."""
        monkeypatch.delenv("GIT_EDITOR", raising=False)
        monkeypatch.setenv("VISUAL", "vim")
        monkeypatch.setenv("EDITOR", "nano")

        assert resolve_editor_command() == "vim"

    def test_falls_back_to_editor(self, monkeypatch) -> None:
        """``EDITOR`` is the last-resort env fallback."""
        monkeypatch.delenv("GIT_EDITOR", raising=False)
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "nano")

        assert resolve_editor_command() == "nano"

    def test_falls_back_to_config_when_env_unset(self, monkeypatch) -> None:
        """``config_editor`` is used only when all env vars are blank."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        assert resolve_editor_command("code --wait") == "code --wait"

    def test_config_editor_is_stripped(self, monkeypatch) -> None:
        """Whitespace around the config-supplied editor is ignored."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        assert resolve_editor_command("  vim  ") == "vim"

    def test_blank_config_editor_returns_none(self, monkeypatch) -> None:
        """A whitespace-only config value falls through to ``None``."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        assert resolve_editor_command("   ") is None

    def test_env_wins_over_config_editor(self, monkeypatch) -> None:
        """Any env var with a value takes priority over the config value."""
        monkeypatch.delenv("GIT_EDITOR", raising=False)
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "nano")

        assert resolve_editor_command("code --wait") == "nano"


class TestFormatMissingEditorMessage:
    """Cover the verbose error string used by both editor flows."""

    def test_mentions_all_three_variables(self) -> None:
        """The base message names every supported environment variable."""
        msg = format_missing_editor_message()

        for key in EDITOR_ENV_VARS:
            assert key in msg

    def test_appends_skip_hint_when_provided(self) -> None:
        """A trailing ``skip_hint`` is appended verbatim."""
        msg = format_missing_editor_message(skip_hint="pass --no-foo.")

        assert msg.endswith("pass --no-foo.")

    def test_mentions_distlift_config_fallback(self) -> None:
        """The message documents the distlift config / env fallback path."""
        msg = format_missing_editor_message()

        assert "editor" in msg
        assert "DISTLIFT_EDITOR" in msg


class TestLaunchEditorBlocking:
    """Cover argv construction, subprocess plumbing, and error paths."""

    def test_raises_configuration_error_when_no_editor(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Without an editor env var, the helper raises a typed error."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        target = tmp_path / "config.toml"
        target.write_text("# stub\n", encoding="utf-8")

        with pytest.raises(ConfigurationError) as excinfo:
            launch_editor_blocking(target)

        # The verbose message should list every supported variable
        for key in EDITOR_ENV_VARS:
            assert key in str(excinfo.value)

    def test_includes_skip_hint_in_error(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """A caller-supplied ``skip_hint`` is surfaced in the raised error."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        target = tmp_path / "config.toml"

        with pytest.raises(ConfigurationError) as excinfo:
            launch_editor_blocking(target, skip_hint="hint-XYZ")

        assert "hint-XYZ" in str(excinfo.value)

    def test_invokes_subprocess_with_resolved_command(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The configured command is split and the path is appended."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("EDITOR", "myeditor --wait")

        target = tmp_path / "config.toml"
        target.write_text("# stub\n", encoding="utf-8")

        captured: dict[str, Any] = {}

        def fake_run(argv, **kwargs):  # noqa: ANN001
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(editor.subprocess, "run", fake_run)

        exit_code = launch_editor_blocking(target)

        assert exit_code == 0
        argv = captured["argv"]
        assert argv[0] == "myeditor"
        assert "--wait" in argv
        assert argv[-1] == str(target)

    def test_returns_subprocess_exit_code(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The editor's exit code is forwarded back to the caller."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("EDITOR", "myeditor")

        target = tmp_path / "config.toml"
        target.write_text("", encoding="utf-8")

        def fake_run(argv, **kwargs):  # noqa: ANN001
            return subprocess.CompletedProcess(argv, 42)

        monkeypatch.setattr(editor.subprocess, "run", fake_run)

        assert launch_editor_blocking(target) == 42

    def test_uses_config_editor_when_env_unset(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """A ``config_editor`` is launched when no env var is set."""
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        target = tmp_path / "config.toml"
        target.write_text("", encoding="utf-8")

        captured: dict[str, Any] = {}

        def fake_run(argv, **kwargs):  # noqa: ANN001
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(editor.subprocess, "run", fake_run)

        exit_code = launch_editor_blocking(
            target, config_editor="myeditor --wait"
        )

        assert exit_code == 0
        assert captured["argv"][0] == "myeditor"
        assert captured["argv"][-1] == str(target)
