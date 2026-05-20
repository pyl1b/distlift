"""Tests for dependencies_autoupdated lifecycle hooks."""

from pathlib import Path

from distlift.config.models import HooksConfig, HookSpec
from distlift.hooks import build_hook_env, run_hook_specs, specs_for_event


class TestDependenciesAutoupdatedHook:
    """Tests for hook environment and event registration."""

    def test_specs_for_event_includes_dependencies_autoupdated(self) -> None:
        """Resolve hook specs for the dependencies_autoupdated event."""
        hooks = HooksConfig(
            dependencies_autoupdated=[HookSpec(argv=["echo", "ok"])],
        )

        specs = specs_for_event(hooks, "dependencies_autoupdated")

        assert len(specs) == 1

    def test_build_hook_env_includes_dependency_fields(self) -> None:
        """Expose dependency update summary variables to hook subprocesses."""
        env = build_hook_env(
            event="dependencies_autoupdated",
            repo_root=Path("/repo"),
            dry_run=False,
            dependency_update_count=2,
            dependency_update_projects=["b", "a"],
            dependency_update_files=["/repo/b/pyproject.toml"],
            dependency_update_dependencies=["pkg-a"],
            dependency_update_triggers=["a"],
        )

        assert env["DISTLIFT_DEPENDENCY_UPDATE_COUNT"] == "2"
        assert env["DISTLIFT_DEPENDENCY_UPDATE_PROJECTS"] == "a,b"
        assert (
            env["DISTLIFT_DEPENDENCY_UPDATE_FILES"] == "/repo/b/pyproject.toml"
        )
        assert env["DISTLIFT_DEPENDENCY_UPDATE_DEPENDENCIES"] == "pkg-a"
        assert env["DISTLIFT_DEPENDENCY_UPDATE_TRIGGERS"] == "a"

    def test_hook_runs_on_disk(self, tmp_path: Path) -> None:
        """Execute a hook command when specs are provided."""
        import sys

        marker = tmp_path / "ran.txt"
        script = (
            f"import pathlib; pathlib.Path({str(marker)!r})"
            ".write_text('ok', encoding='utf-8')"
        )
        hooks = HooksConfig(
            dependencies_autoupdated=[
                HookSpec(argv=[sys.executable, "-c", script]),
            ],
        )
        specs = specs_for_event(hooks, "dependencies_autoupdated")
        env = build_hook_env(
            event="dependencies_autoupdated",
            repo_root=tmp_path,
            dry_run=False,
            dependency_update_count=1,
            dependency_update_projects=["b"],
            dependency_update_files=[str(tmp_path / "b.toml")],
            dependency_update_dependencies=["a"],
            dependency_update_triggers=["a"],
        )

        run_hook_specs(specs, repo_root=tmp_path, extra_env=env)

        assert marker.read_text(encoding="utf-8") == "ok"
