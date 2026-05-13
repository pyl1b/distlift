from pathlib import Path

from distlift.config.models import ResolvedConfig, VersionSource
from distlift.languages.javascript import JavaScriptProjectAdapter


def _config(**kwargs) -> ResolvedConfig:
    from distlift.config.models import ReleaseMode, VersionFormat

    defaults = dict(
        mode=ReleaseMode.SIMPLE,
        default_version="1.0.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        version_source=VersionSource.MANIFEST,
    )
    defaults.update(kwargs)
    return ResolvedConfig(**defaults)


class TestJavaScriptProjectAdapter:
    def test_detects_package_json(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name":"x","version":"1.0.0"}')
        adapter = JavaScriptProjectAdapter()
        assert adapter.detect_project(tmp_path)

    def test_read_manifest_version(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name":"x","version":"2.3.4"}')
        config = _config()
        adapter = JavaScriptProjectAdapter()
        target = adapter.load_release_target(tmp_path, config)
        assert adapter.read_manifest_version(target) == "2.3.4"

    def test_update_manifest_version(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name":"x","version":"1.0.0"}')
        config = _config()
        adapter = JavaScriptProjectAdapter()
        target = adapter.load_release_target(tmp_path, config)
        adapter.update_manifest_version(target, "3.0.0")
        assert adapter.read_manifest_version(target) == "3.0.0"
