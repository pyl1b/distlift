"""Tests for user/system config file creation and editor opening."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from distlift import editor as editor_module
from distlift.config import files as files_module
from distlift.config.files import (
    STUB_CONFIG_CONTENT,
    ConfigScope,
    create_config_file,
    get_system_config_path,
    get_user_config_path,
    open_config_file_in_editor,
)
from distlift.editor import EDITOR_ENV_VARS
from distlift.errors import ConfigurationError


@pytest.fixture
def fake_user_path(tmp_path: Path, monkeypatch) -> Path:
    """Redirect user config lookups to a temporary file path.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture for module patches.
    """
    target = tmp_path / "user_root" / "distlift" / "config.toml"
    monkeypatch.setattr(files_module, "DEFAULT_USER_CONFIG_PATHS", [target])
    return target


@pytest.fixture
def fake_system_path(tmp_path: Path, monkeypatch) -> Path:
    """Redirect system config lookups to a temporary file path.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture for module patches.
    """
    target = tmp_path / "system_root" / "distlift" / "config.toml"
    monkeypatch.setattr(files_module, "DEFAULT_SYSTEM_CONFIG_PATHS", [target])
    return target


class TestGetConfigPath:
    """Cover path resolution and missing-location errors."""

    def test_user_path_returns_first_candidate(
        self, fake_user_path: Path
    ) -> None:
        """``get_user_config_path`` returns the configured user path."""
        assert get_user_config_path() == fake_user_path

    def test_system_path_returns_first_candidate(
        self, fake_system_path: Path
    ) -> None:
        """``get_system_config_path`` returns the configured system path."""
        assert get_system_config_path() == fake_system_path

    def test_user_raises_when_no_candidate(self, monkeypatch) -> None:
        """An empty candidate list yields a ``ConfigurationError``."""
        monkeypatch.setattr(files_module, "DEFAULT_USER_CONFIG_PATHS", [])

        with pytest.raises(ConfigurationError) as excinfo:
            get_user_config_path()

        # The hint should mention the relevant Windows env var
        assert "APPDATA" in str(excinfo.value)

    def test_system_raises_when_no_candidate(self, monkeypatch) -> None:
        """An empty system candidate list yields a ``ConfigurationError``."""
        monkeypatch.setattr(files_module, "DEFAULT_SYSTEM_CONFIG_PATHS", [])

        with pytest.raises(ConfigurationError) as excinfo:
            get_system_config_path()

        assert "ProgramData" in str(excinfo.value)


class TestCreateConfigFile:
    """Cover stub seeding and overwrite semantics."""

    def test_creates_user_file_when_missing(
        self, fake_user_path: Path
    ) -> None:
        """A new file is written with the documented stub contents."""
        path, created = create_config_file(ConfigScope.USER)

        assert created is True
        assert path == fake_user_path
        assert path.is_file()
        assert path.read_text(encoding="utf-8") == STUB_CONFIG_CONTENT

    def test_creates_parent_directories(self, fake_user_path: Path) -> None:
        """Intermediate parent directories are created on demand."""
        assert not fake_user_path.parent.exists()

        create_config_file(ConfigScope.USER)

        assert fake_user_path.parent.is_dir()

    def test_does_not_overwrite_existing_without_force(
        self, fake_user_path: Path
    ) -> None:
        """Existing files are preserved unless ``force=True`` is passed."""
        fake_user_path.parent.mkdir(parents=True, exist_ok=True)
        fake_user_path.write_text("# kept\n", encoding="utf-8")

        path, created = create_config_file(ConfigScope.USER)

        assert created is False
        assert path == fake_user_path
        assert path.read_text(encoding="utf-8") == "# kept\n"

    def test_force_overwrites_existing_file(
        self, fake_user_path: Path
    ) -> None:
        """``force=True`` replaces existing contents with the stub."""
        fake_user_path.parent.mkdir(parents=True, exist_ok=True)
        fake_user_path.write_text("# kept\n", encoding="utf-8")

        path, created = create_config_file(ConfigScope.USER, force=True)

        assert created is True
        assert path.read_text(encoding="utf-8") == STUB_CONFIG_CONTENT

    def test_creates_system_file_when_missing(
        self, fake_system_path: Path
    ) -> None:
        """The system scope writes to the system-scope candidate path."""
        path, created = create_config_file(ConfigScope.SYSTEM)

        assert created is True
        assert path == fake_system_path
        assert path.is_file()


class TestOpenConfigFileInEditor:
    """Cover editor launch, auto-create, and error paths."""

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
            config_editor: Value returned by the patched global-editor
                resolver, simulating what a real user/system TOML layer
                would provide. ``None`` disables the config fallback.
        """
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("EDITOR", "myeditor")

        # Avoid hitting real user/system config files when resolving the
        # configured editor fallback during tests
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

    def test_creates_stub_then_opens_editor(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """When the file is missing, a stub is seeded before editing."""
        captured = self._stub_editor(monkeypatch)

        path, exit_code = open_config_file_in_editor(ConfigScope.USER)

        assert path == fake_user_path
        assert exit_code == 0
        assert fake_user_path.is_file()
        assert captured["argv"][-1] == str(fake_user_path)

    def test_refuses_when_missing_and_no_create(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """``create_if_missing=False`` raises when the file is absent."""
        self._stub_editor(monkeypatch)

        with pytest.raises(ConfigurationError) as excinfo:
            open_config_file_in_editor(
                ConfigScope.USER, create_if_missing=False
            )

        assert "init-user" in str(excinfo.value)
        assert not fake_user_path.exists()

    def test_opens_existing_file_without_overwriting(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """An existing file is opened and its contents are preserved."""
        fake_user_path.parent.mkdir(parents=True, exist_ok=True)
        fake_user_path.write_text("# kept\n", encoding="utf-8")
        self._stub_editor(monkeypatch)

        open_config_file_in_editor(ConfigScope.USER)

        assert fake_user_path.read_text(encoding="utf-8") == "# kept\n"

    def test_forwards_editor_exit_code(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """The editor's non-zero exit status is propagated to the caller."""
        self._stub_editor(monkeypatch, exit_code=7)

        _, exit_code = open_config_file_in_editor(ConfigScope.USER)

        assert exit_code == 7

    def test_uses_config_editor_when_env_unset(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """When env vars are unset, the merged ``editor`` setting is used."""
        captured = self._stub_editor(monkeypatch, config_editor="code --wait")

        # Remove the env editor that ``_stub_editor`` defaulted to so the
        # config fallback is the only available source
        monkeypatch.delenv("EDITOR", raising=False)

        open_config_file_in_editor(ConfigScope.USER)

        argv = captured["argv"]
        assert argv[0] == "code"
        assert "--wait" in argv
        assert argv[-1] == str(fake_user_path)

    def test_raises_when_no_env_and_no_config(
        self, fake_user_path: Path, monkeypatch
    ) -> None:
        """Without env vars and config editor, a typed error is raised."""
        self._stub_editor(monkeypatch, config_editor=None)
        for key in EDITOR_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        with pytest.raises(ConfigurationError) as excinfo:
            open_config_file_in_editor(ConfigScope.USER)

        # The verbose message should mention the configured fallback too
        message = str(excinfo.value)
        assert "DISTLIFT_EDITOR" in message
        for key in EDITOR_ENV_VARS:
            assert key in message
