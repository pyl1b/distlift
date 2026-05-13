from pathlib import Path

from distlift.config.models import Language, ResolvedConfig, VersionSource
from distlift.languages.python import PythonProjectAdapter
from distlift.release.models import ReleaseTarget


def _config(**kwargs) -> ResolvedConfig:
    from distlift.config.models import ReleaseMode, VersionFormat

    defaults = dict(
        mode=ReleaseMode.SIMPLE,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        version_source=VersionSource.MANIFEST,
    )
    defaults.update(kwargs)
    return ResolvedConfig(**defaults)


class TestPythonProjectAdapter:
    def test_detects_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        adapter = PythonProjectAdapter()
        assert adapter.detect_project(tmp_path)

    def test_no_detection_without_file(self, tmp_path: Path):
        adapter = PythonProjectAdapter()
        assert not adapter.detect_project(tmp_path)

    def test_read_manifest_version(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "1.2.3"\n'
        )
        config = _config()
        adapter = PythonProjectAdapter()
        target = adapter.load_release_target(tmp_path, config)
        assert adapter.read_manifest_version(target) == "1.2.3"

    def test_dynamic_version_detected(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndynamic = ["version"]\n'
        )
        config = _config()
        adapter = PythonProjectAdapter()
        target = adapter.load_release_target(tmp_path, config)
        assert adapter.is_dynamic_version(target)

    def test_update_manifest_version(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n'
        )
        config = _config()
        adapter = PythonProjectAdapter()
        target = adapter.load_release_target(tmp_path, config)
        adapter.update_manifest_version(target, "2.0.0")
        assert adapter.read_manifest_version(target) == "2.0.0"
