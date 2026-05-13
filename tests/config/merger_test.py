"""Tests for merging layered distlift configuration fragments."""

from distlift.config.merger import merge_config_layers
from distlift.config.models import Language, RawConfig, VersionFormat


class TestMergeConfigLayers:
    """Tests for configuration layer precedence and source tracking."""

    def test_empty_layers_returns_defaults(self) -> None:
        """Use built-in defaults when no config layers are supplied."""

        # Merge an empty layer list.
        config = merge_config_layers([])

        # Confirm default release values are present.
        assert config.default_version == "0.1.0"
        assert config.remotes == ["origin"]

    def test_later_layer_wins(self) -> None:
        """Prefer values from later configuration layers."""

        # Build two layers that set the same field differently.
        layer1 = RawConfig(language=Language.PYTHON, source="file1")
        layer2 = RawConfig(language=Language.JAVASCRIPT, source="file2")

        # Merge the layers in precedence order.
        config = merge_config_layers([layer1, layer2])

        # Confirm the later layer overrides the earlier one.
        assert config.language == Language.JAVASCRIPT

    def test_field_sources_tracked(self) -> None:
        """Record the source that provided each merged field."""

        # Build a layer with a distinct source name.
        layer = RawConfig(language=Language.PYTHON, source="my_config.toml")

        # Merge the layer and inspect source metadata.
        config = merge_config_layers([layer])

        # Confirm the language field source is preserved.
        assert config.field_sources.get("language") == "my_config.toml"

    def test_remotes_replaced_by_last_nonempty(self) -> None:
        """Replace remotes with the last non-empty remote list."""

        # Build layers that each provide a remote list.
        layer1 = RawConfig(remotes=["origin"], source="a")
        layer2 = RawConfig(remotes=["upstream"], source="b")

        # Merge the layers in precedence order.
        config = merge_config_layers([layer1, layer2])

        # Confirm the later non-empty remote list wins.
        assert config.remotes == ["upstream"]

    def test_version_format_propagated(self) -> None:
        """Propagate the version format from a raw layer."""

        # Build a layer that configures a major-only version format.
        layer = RawConfig(version_format=VersionFormat.MAJOR, source="x")

        # Merge the layer into a resolved config.
        config = merge_config_layers([layer])

        # Confirm the configured version format is retained.
        assert config.version_format == VersionFormat.MAJOR

    def test_changelog_overlay_merge(self) -> None:
        """Merge shallow changelog overlay keys across layers."""

        layer1 = RawConfig(
            changelog_overlay={"path": "A.md"},
            source="a",
        )

        layer2 = RawConfig(
            changelog_overlay={"enabled": False, "prompt_editor": False},
            source="b",
        )

        config = merge_config_layers([layer1, layer2])

        assert config.changelog.path == "A.md"
        assert config.changelog.enabled is False
        assert config.changelog.prompt_editor is False

    def test_editor_defaults_to_none(self) -> None:
        """A merged config exposes ``editor=None`` when no layer sets it."""

        # Merge a layer that does not configure the editor field.
        config = merge_config_layers([RawConfig(source="a")])

        # Confirm the default is ``None`` for downstream callers.
        assert config.editor is None

    def test_editor_propagated_and_overrides(self) -> None:
        """Later layers override the earlier editor and field source updates."""

        layer1 = RawConfig(editor="nano", source="user")
        layer2 = RawConfig(editor="code --wait", source="environment")

        config = merge_config_layers([layer1, layer2])

        assert config.editor == "code --wait"
        assert config.field_sources.get("editor") == "environment"
