from distlift.config.merger import merge_config_layers
from distlift.config.models import Language, RawConfig, VersionFormat


class TestMergeConfigLayers:
    def test_empty_layers_returns_defaults(self):
        config = merge_config_layers([])
        assert config.default_version == "0.1.0"
        assert config.remotes == ["origin"]

    def test_later_layer_wins(self):
        layer1 = RawConfig(language=Language.PYTHON, source="file1")
        layer2 = RawConfig(language=Language.JAVASCRIPT, source="file2")
        config = merge_config_layers([layer1, layer2])
        assert config.language == Language.JAVASCRIPT

    def test_field_sources_tracked(self):
        layer = RawConfig(language=Language.PYTHON, source="my_config.toml")
        config = merge_config_layers([layer])
        assert config.field_sources.get("language") == "my_config.toml"

    def test_remotes_replaced_by_last_nonempty(self):
        layer1 = RawConfig(remotes=["origin"], source="a")
        layer2 = RawConfig(remotes=["upstream"], source="b")
        config = merge_config_layers([layer1, layer2])
        assert config.remotes == ["upstream"]

    def test_version_format_propagated(self):
        layer = RawConfig(version_format=VersionFormat.MAJOR, source="x")
        config = merge_config_layers([layer])
        assert config.version_format == VersionFormat.MAJOR
