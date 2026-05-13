from distlift.config.loader import load_environment_config


class TestLoadEnvironmentConfig:
    def test_parses_language(self):
        data = load_environment_config({"DISTLIFT_LANGUAGE": "python"})
        assert data["language"] == "python"

    def test_parses_remotes(self):
        data = load_environment_config({"DISTLIFT_REMOTES": "origin,upstream"})
        assert data["remotes"] == ["origin", "upstream"]

    def test_empty_env_returns_empty(self):
        data = load_environment_config({})
        assert data == {}

    def test_plugin_paths(self):
        data = load_environment_config({"DISTLIFT_PLUGIN_PATHS": "a.py,b.py"})
        assert data["plugins"]["paths"] == ["a.py", "b.py"]
