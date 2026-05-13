"""Tests for loading distlift configuration from environment variables."""

from distlift.config.loader import load_environment_config


class TestLoadEnvironmentConfig:
    """Tests for environment-backed raw configuration loading."""

    def test_parses_language(self) -> None:
        """Parse the configured language from the environment."""

        # Load an environment containing the language variable.
        data = load_environment_config({"DISTLIFT_LANGUAGE": "python"})

        # Confirm the language value is copied into the raw config.
        assert data["language"] == "python"

    def test_parses_remotes(self) -> None:
        """Parse a comma-separated remote list from the environment."""

        # Load an environment containing multiple remotes.
        data = load_environment_config({"DISTLIFT_REMOTES": "origin,upstream"})

        # Confirm remotes are split into an ordered list.
        assert data["remotes"] == ["origin", "upstream"]

    def test_empty_env_returns_empty(self) -> None:
        """Return an empty raw config when no variables are present."""

        # Load a config from an environment without distlift variables.
        data = load_environment_config({})

        # Confirm no defaults are injected by the environment loader.
        assert data == {}

    def test_plugin_paths(self) -> None:
        """Parse plugin file paths from a comma-separated variable."""

        # Load an environment containing explicit plugin paths.
        data = load_environment_config({"DISTLIFT_PLUGIN_PATHS": "a.py,b.py"})

        # Confirm plugin paths are nested under the plugin config key.
        assert data["plugins"]["paths"] == ["a.py", "b.py"]

    def test_parses_editor(self) -> None:
        """``DISTLIFT_EDITOR`` is exposed as a top-level ``editor`` string."""

        # Load an environment specifying a custom editor command.
        data = load_environment_config({"DISTLIFT_EDITOR": "code --wait"})

        # Confirm the editor value flows into the raw config dict.
        assert data["editor"] == "code --wait"

    def test_blank_editor_is_ignored(self) -> None:
        """A whitespace-only ``DISTLIFT_EDITOR`` is treated as unset."""

        # Load an environment with a blank editor value.
        data = load_environment_config({"DISTLIFT_EDITOR": "   "})

        # Confirm the blank value is not propagated to the raw config.
        assert "editor" not in data
