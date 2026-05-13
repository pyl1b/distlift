"""Tests for loading distlift configuration from environment variables."""

import pytest

from distlift.config.loader import _parse_raw_config, load_environment_config
from distlift.config.models import Language, VersionSource
from distlift.errors import ConfigurationError


class TestParseRawConfigMonorepoPackages:
    """Tests for ``[monorepo].packages`` shorthand and table entries."""

    def test_packages_as_strings_derive_names(self) -> None:
        """List package roots; ``name`` is the last path segment."""

        data = {
            "monorepo": {
                "packages": [
                    "resi_core",
                    "libs/resi_drf",
                ],
            },
        }

        raw = _parse_raw_config(data, "test")

        assert len(raw.monorepo.packages) == 2
        assert raw.monorepo.packages[0].name == "resi_core"
        assert raw.monorepo.packages[0].path == "resi_core"
        assert raw.monorepo.packages[1].name == "resi_drf"
        assert raw.monorepo.packages[1].path == "libs/resi_drf"

    def test_packages_mixed_strings_and_tables(self) -> None:
        """Allow path strings alongside explicit ``[[monorepo.packages]]`` rows."""

        data = {
            "monorepo": {
                "packages": [
                    "plain_pkg",
                    {
                        "name": "explicit",
                        "path": "somewhere/explicit",
                    },
                ],
            },
        }

        raw = _parse_raw_config(data, "test")

        assert raw.monorepo.packages[0].name == "plain_pkg"
        assert raw.monorepo.packages[0].path == "plain_pkg"
        assert raw.monorepo.packages[1].name == "explicit"
        assert raw.monorepo.packages[1].path == "somewhere/explicit"

    def test_packages_table_with_optional_fields(self) -> None:
        """Table entries preserve per-package overrides."""

        data = {
            "monorepo": {
                "packages": [
                    {
                        "name": "js_pkg",
                        "path": "packages/js_pkg",
                        "language": "javascript",
                        "version_source": "tag",
                    },
                ],
            },
        }

        raw = _parse_raw_config(data, "test")
        pkg = raw.monorepo.packages[0]

        assert pkg.language == Language.JAVASCRIPT
        assert pkg.version_source == VersionSource.TAG

    def test_empty_string_path_raises(self) -> None:
        """Reject blank path strings in the shorthand form."""

        data = {"monorepo": {"packages": ["   "]}}

        with pytest.raises(ConfigurationError):
            _parse_raw_config(data, "test")

    def test_non_string_table_entry_raises(self) -> None:
        """Reject entries that are neither a path string nor a table."""

        data = {"monorepo": {"packages": [42]}}

        with pytest.raises(ConfigurationError):
            _parse_raw_config(data, "test")


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
