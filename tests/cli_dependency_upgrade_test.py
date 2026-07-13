"""CLI tests for distlift deps upgrade."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from distlift.cli import app
from distlift.config.models import Language
from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
)
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencySelection,
    DependencyUpgradePlan,
    DependencyUpgradeResult,
    PackageSource,
    SourceUpgradePlan,
    SourceUpgradeResult,
)


class TestDepsUpgradeCli:
    """Tests for the deps upgrade command."""

    def test_non_tty_exits_with_error(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "distlift.cli._terminal_is_interactive",
            lambda: False,
        )
        runner = CliRunner()
        result = runner.invoke(app, ["deps", "upgrade"])
        assert result.exit_code == 1
        assert "interactive terminal" in (result.stdout + result.stderr)

    def test_dry_run_with_scripted_selector(
        self,
        tmp_python_project: Path,
        monkeypatch,
    ) -> None:
        manifest = tmp_python_project / "pyproject.toml"
        manifest.write_text(
            """
[project]
name = "mypackage"
version = "0.1.0"
dependencies = ["attrs>=23.0"]
""".strip(),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "distlift.cli._terminal_is_interactive",
            lambda: True,
        )

        dep = DeclaredDependency(
            name="attrs",
            group="dependencies",
            constraint=">=23.0",
            location_key="k",
        )
        source = PackageSource(
            project=DependencyProject(
                name="mypackage",
                dependency_name="mypackage",
                language=Language.PYTHON,
                root=tmp_python_project,
                manifest_path=manifest,
            ),
            manager_name="pip",
        )
        selection = DependencySelection(
            dependency=dep,
            target_version="25.0.0",
            cycle_index=0,
        )
        plan = DependencyUpgradePlan(
            repo_root=tmp_python_project,
            sources=(
                SourceUpgradePlan(
                    source=source,
                    selections=(selection,),
                    manifest_path=manifest,
                    planned_changes=(
                        DependencyUpdateChange(
                            project_name="mypackage",
                            dependency_name="attrs",
                            manifest_path=manifest,
                            old_specifier=">=23.0",
                            new_specifier=">=25.0.0",
                        ),
                    ),
                ),
            ),
            dry_run=True,
        )
        result = DependencyUpgradeResult(
            success=True,
            source_results=[
                SourceUpgradeResult(
                    source_name="mypackage",
                    manifest_changes=list(plan.sources[0].planned_changes),
                )
            ],
        )

        def fake_run_dependency_upgrade(self, repo_root, config, **kwargs):
            kwargs["confirm_callback"](plan)
            return result

        monkeypatch.setattr(
            "distlift.app.DistliftApplication.run_dependency_upgrade",
            fake_run_dependency_upgrade,
        )

        runner = CliRunner()
        invoke = runner.invoke(
            app,
            [
                "deps",
                "upgrade",
                "--repo-root",
                str(tmp_python_project),
                "--dry-run",
            ],
        )
        assert invoke.exit_code == 0
        assert "would update" in invoke.stdout
