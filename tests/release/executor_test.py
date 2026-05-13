import logging
from pathlib import Path

from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
    VersionSource,
)
from distlift.errors import ChangelogError
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.release.executor import (
    ReleaseExecutor,
    _log_release_execution_failure,
)
from distlift.release.models import (
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
)
from distlift.versioning.models import ResolvedVersion, VersionParts


def _make_registry():
    manager = PluginManager()
    return manager.build_registry(PluginLoadRequest())


class TestDryRunExecution:
    def test_dry_run_returns_success(self, tmp_python_project: Path):
        registry = _make_registry()
        current = VersionParts(major=0, minor=1, patch=0)
        next_v = VersionParts(major=0, minor=1, patch=1)
        resolved = ResolvedVersion(
            current=current,
            next=next_v,
            tag_name="v0.1.1",
            bump=BumpKind.PATCH,
            was_explicit=False,
        )
        target = ReleaseTarget(
            language=Language.PYTHON,
            root=tmp_python_project,
            manifest_path=tmp_python_project / "pyproject.toml",
            version_source=VersionSource.MANIFEST,
        )
        pkg_plan = PackageReleasePlan(
            target=target, resolved_version=resolved, update_manifest=True
        )
        plan = ReleasePlan(
            mode=ReleaseMode.SIMPLE,
            packages=[pkg_plan],
            commit_message="chore: release 0.1.1",
            tag_names=["v0.1.1"],
            remotes=["origin"],
            dry_run=True,
            repo_root=tmp_python_project,
        )
        executor = ReleaseExecutor(registry=registry)
        result = executor.execute(plan, ResolvedConfig())
        assert result.success
        assert result.dry_run
        assert result.tag_names == ["v0.1.1"]


class TestReleaseExecutionFailureLogging:
    def test_distlift_error_emits_no_error_log_record(self, caplog):
        """Expected ``DistliftError`` failures avoid ERROR noise (CLI prints)."""
        caplog.set_level(logging.ERROR, logger="distlift.release.executor")

        _log_release_execution_failure(ChangelogError("changelog problem"))

        assert not caplog.records

    def test_unexpected_error_emits_error_log_record(self, caplog):
        """Unexpected exceptions still produce an ERROR log line."""
        caplog.set_level(logging.ERROR, logger="distlift.release.executor")

        _log_release_execution_failure(ValueError("boom"))

        assert caplog.records
        assert caplog.records[0].levelno == logging.ERROR
        assert "boom" in caplog.text
