import subprocess
from pathlib import Path

import pytest

from distlift.app import DistliftApplication
from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
    VersionSource,
)
from distlift.release.models import SimpleReleaseRequest


def _make_config(**kwargs) -> ResolvedConfig:
    defaults = dict(
        language=Language.PYTHON,
        mode=ReleaseMode.SIMPLE,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        version_source=VersionSource.MANIFEST,
    )
    defaults.update(kwargs)
    return ResolvedConfig(**defaults)


class TestSimpleReleasePlan:
    def test_dry_run_produces_result(self, tmp_python_project: Path):
        config = _make_config()
        app = DistliftApplication()
        request = SimpleReleaseRequest(
            repo_root=tmp_python_project,
            config=config,
            bump=BumpKind.PATCH,
            dry_run=True,
        )
        result = app.run_simple_release(request)
        assert result.success
        assert result.dry_run
        assert "v0.1.1" in result.tag_names

    def test_explicit_version_dry_run(self, tmp_python_project: Path):
        config = _make_config()
        app = DistliftApplication()
        request = SimpleReleaseRequest(
            repo_root=tmp_python_project,
            config=config,
            explicit_version="5.0.0",
            dry_run=True,
        )
        result = app.run_simple_release(request)
        assert result.success
        assert "v5.0.0" in result.tag_names

    def test_dirty_worktree_fails(self, tmp_python_project: Path):
        (tmp_python_project / "dirty.txt").write_text("x")
        subprocess.run(
            ["git", "add", "."], cwd=tmp_python_project, check=True, capture_output=True
        )
        config = _make_config()
        app = DistliftApplication()
        request = SimpleReleaseRequest(
            repo_root=tmp_python_project,
            config=config,
            bump=BumpKind.PATCH,
            dry_run=True,
        )
        result = app.run_simple_release(request)
        assert not result.success
