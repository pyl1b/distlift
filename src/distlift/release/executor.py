from __future__ import annotations

import attrs

from distlift.changelog.builder import render_inserted_entry_preview
from distlift.changelog.editor_prompt import maybe_prompt_edit_changelog_entry
from distlift.changelog.writer import write_changelog_document
from distlift.config.models import Language, ResolvedConfig
from distlift.dependencies.models import (
    DependencyUpdateRequest,
    DependencyUpdateResult,
)
from distlift.dependencies.projects import released_versions_from_plan
from distlift.dependencies.service import run_dependency_updates
from distlift.errors import DistliftError, HookExecutionError
from distlift.hooks import build_hook_env, run_hook_specs, specs_for_event
from distlift.languages.base import ProjectAdapter
from distlift.logging_utils import TRACE, get_logger
from distlift.plugins.registry import PluginRegistry
from distlift.release.models import ReleasePlan, ReleaseResult
from distlift.release.planner import build_tag_messages
from distlift.vcs.git import GitRepository

log = get_logger(__name__)


def _log_release_execution_failure(exc: BaseException) -> None:
    """Emit a log record for a failed release execution.

    Expected :class:`DistliftError` values are omitted at ERROR so callers can
    surface ``str(exc)`` once (for example the CLI) without duplicating text or
    printing tracebacks; they are still logged at TRACE with ``exc_info`` for
    ``--verbose`` runs. Unexpected exceptions log at ERROR with a traceback.

    Args:
        exc: Exception raised while executing the release plan.
    """
    if isinstance(exc, DistliftError):
        log.log(
            TRACE,
            "Release execution failed: %s",
            exc,
            exc_info=True,
        )

        return

    log.error(
        "Release execution failed: %s",
        exc,
        exc_info=True,
    )


def _get_adapter(
    registry: PluginRegistry, language: Language
) -> ProjectAdapter:
    """Return a project adapter for the registered language plugin.

    Args:
        registry: Active plugin registry.
        language: Language enum member to resolve.
    """
    from distlift.languages.javascript import (
        JavaScriptProjectAdapter,
        JavaScriptProjectPlugin,
    )
    from distlift.languages.python import (
        PythonProjectAdapter,
        PythonProjectPlugin,
    )

    plugin = registry.get_language_plugin(language.value)
    if isinstance(plugin, PythonProjectPlugin):
        return PythonProjectAdapter()
    if isinstance(plugin, JavaScriptProjectPlugin):
        return JavaScriptProjectAdapter()
    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"No adapter for plugin: {plugin.get_name()}"
    )


@attrs.define
class ReleaseExecutor:
    """Applies a release plan: manifests, commit, tags, and pushes.

    Attributes:
        registry: Plugin registry used to resolve language adapters.
    """

    registry: PluginRegistry

    def execute(
        self, plan: ReleasePlan, config: ResolvedConfig
    ) -> ReleaseResult:
        """Run the plan or return a dry-run summary without side effects.

        Args:
            plan: Fully built release plan for this repository.
            config: Effective configuration including hook command lists.
        """
        if plan.dry_run:
            return self._dry_run_result(plan, config)

        git = GitRepository(root=plan.repo_root)
        push_failed = False
        commit_sha: str | None = None
        pushed_remotes: list[str] = []

        try:
            self._apply_changelog_updates(plan)
            self._apply_manifest_updates(plan)
            dependency_results = self._apply_dependency_updates(plan, config)
            self._invoke_dependencies_autoupdated_hook(
                config, plan, dependency_results
            )
            commit_sha = self._commit_release(plan, git, dependency_results)
            self._create_tags(plan, git)

            try:
                self._push_release(plan, git, pushed_remotes)
            except Exception as push_exc:
                push_failed = True

                # Run tag-push failure hooks with best-effort partial remotes
                try:
                    self._invoke_hook_event(
                        config,
                        "tag_push_failed",
                        plan,
                        commit_sha=commit_sha,
                        pushed_remotes=pushed_remotes,
                        error=str(push_exc),
                        dry_run=False,
                    )
                except HookExecutionError as hook_exc:
                    log.error(
                        "tag_push_failed hook failed: %s",
                        hook_exc,
                        exc_info=True,
                    )

                    return ReleaseResult(
                        success=False,
                        dry_run=False,
                        tag_names=plan.tag_names,
                        commit_sha=commit_sha,
                        pushed_remotes=pushed_remotes,
                        error=str(hook_exc),
                    )

                raise push_exc from push_exc

            if pushed_remotes:
                self._invoke_hook_event(
                    config,
                    "tag_pushed",
                    plan,
                    commit_sha=commit_sha,
                    pushed_remotes=pushed_remotes,
                    error=None,
                    dry_run=False,
                )

            return ReleaseResult(
                success=True,
                dry_run=False,
                tag_names=plan.tag_names,
                commit_sha=commit_sha,
                pushed_remotes=pushed_remotes,
                dependency_updates=dependency_results,
            )

        except HookExecutionError as exc:
            log.error("Hook execution failed: %s", exc, exc_info=True)

            return ReleaseResult(
                success=False,
                dry_run=False,
                tag_names=plan.tag_names,
                commit_sha=commit_sha,
                pushed_remotes=pushed_remotes,
                error=str(exc),
            )

        except Exception as exc:
            if not push_failed:
                try:
                    self._invoke_hook_event(
                        config,
                        "release_failed",
                        plan,
                        commit_sha=commit_sha,
                        pushed_remotes=pushed_remotes or None,
                        error=str(exc),
                        dry_run=False,
                    )
                except HookExecutionError as hook_exc:
                    log.error(
                        "release_failed hook failed: %s",
                        hook_exc,
                        exc_info=True,
                    )

                    _log_release_execution_failure(exc)

                    return ReleaseResult(
                        success=False,
                        dry_run=False,
                        tag_names=plan.tag_names,
                        commit_sha=commit_sha,
                        pushed_remotes=pushed_remotes,
                        error=str(hook_exc),
                    )

            _log_release_execution_failure(exc)

            return ReleaseResult(
                success=False,
                dry_run=False,
                tag_names=plan.tag_names,
                error=str(exc),
            )

    def _invoke_hook_event(
        self,
        config: ResolvedConfig,
        event_name: str,
        plan: ReleasePlan,
        *,
        commit_sha: str | None,
        pushed_remotes: list[str] | None,
        error: str | None,
        dry_run: bool,
    ) -> None:
        """Run all hooks for one event when the list is non-empty.

        Args:
            config: Resolved configuration with merged hook specs.
            event_name: Attribute name on ``HooksConfig``.
            plan: Active release plan (supplies repo root and tag names).
            commit_sha: Current commit hash when known.
            pushed_remotes: Remotes successfully pushed, or partial list on
                push failure.
            error: Human-readable error string for failure events.
            dry_run: When True, skip (callers use False after dry-run return).
        """
        if dry_run:
            return

        specs = specs_for_event(config.hooks, event_name)

        if not specs:
            return

        extra = build_hook_env(
            event=event_name,
            repo_root=plan.repo_root,
            dry_run=dry_run,
            tag_names=plan.tag_names,
            pushed_remotes=pushed_remotes,
            commit_sha=commit_sha,
            error=error,
        )
        run_hook_specs(
            specs,
            repo_root=plan.repo_root,
            extra_env=extra,
        )

    def _apply_changelog_updates(self, plan: ReleasePlan) -> None:
        """Write changelog documents described by the plan.

        Args:
            plan: Release plan possibly containing per-package changelog plans.
        """
        for pkg_plan in plan.packages:
            update_plan = pkg_plan.changelog_update

            if update_plan is None:
                continue

            update_plan = maybe_prompt_edit_changelog_entry(
                update_plan,
                changelog_prompt_editor=plan.changelog_prompt_editor,
                skip_changelog_editor=plan.skip_changelog_editor,
                dry_run=plan.dry_run,
                editor_command=plan.editor_command,
            )

            log.info("Writing changelog %s", update_plan.path)
            write_changelog_document(
                update_plan.path,
                update_plan.new_document,
            )

    def _apply_manifest_updates(self, plan: ReleasePlan) -> None:
        """Write next versions into manifests when the plan requires it.

        Args:
            plan: Release plan whose packages may need manifest updates.
        """
        for pkg_plan in plan.packages:
            if not pkg_plan.update_manifest:
                log.debug(
                    "Skipping manifest update for %s (dynamic version)",
                    pkg_plan.target.package_name or "package",
                )
                continue

            adapter = _get_adapter(self.registry, pkg_plan.target.language)
            version_str = str(pkg_plan.resolved_version.next)
            log.info(
                "Updating manifest %s to %s",
                pkg_plan.target.manifest_path,
                version_str,
            )
            adapter.update_manifest_version(pkg_plan.target, version_str)

    def _build_dependency_update_request(
        self, plan: ReleasePlan, config: ResolvedConfig
    ) -> DependencyUpdateRequest:
        """Build a dependency update request from the active release plan.

        Args:
            plan: Active release plan with next versions per package.
            config: Effective merged configuration.
        """
        released = released_versions_from_plan(plan)

        return DependencyUpdateRequest(
            repo_root=plan.repo_root,
            config=config,
            plan=plan,
            released_versions=released,
            dry_run=plan.dry_run,
            run_source="release",
        )

    def _apply_dependency_updates(
        self, plan: ReleasePlan, config: ResolvedConfig
    ) -> list[DependencyUpdateResult]:
        """Run dependency autoupdates after manifest version writes.

        Args:
            plan: Active release plan.
            config: Effective merged configuration.
        """
        if not config.dependency_updates.enabled:
            return []

        request = self._build_dependency_update_request(plan, config)
        results = run_dependency_updates(request, self.registry)
        self._log_dependency_update_results(results)

        return results

    def _log_dependency_update_results(
        self, results: list[DependencyUpdateResult]
    ) -> None:
        """Log each planned or applied dependency declaration change.

        Args:
            results: Results returned by dependency updaters.
        """
        for result in results:
            for change in result.changes:
                log.info(
                    "Dependency update %s: %s %s -> %s in %s",
                    change.project_name,
                    change.dependency_name,
                    change.old_specifier,
                    change.new_specifier,
                    change.manifest_path,
                )

            for warning in result.warnings:
                log.warning("%s: %s", result.updater_name, warning)

    def _invoke_dependencies_autoupdated_hook(
        self,
        config: ResolvedConfig,
        plan: ReleasePlan,
        results: list[DependencyUpdateResult],
    ) -> None:
        """Run ``dependencies_autoupdated`` hooks when changes were written.

        Args:
            config: Resolved configuration with hook command lists.
            plan: Active release plan.
            results: Dependency update results from this run.
        """
        if plan.dry_run:
            return

        all_changes = [c for r in results for c in r.changes]

        if not all_changes:
            return

        specs = specs_for_event(config.hooks, "dependencies_autoupdated")

        if not specs:
            return

        projects = sorted({c.project_name for c in all_changes})
        files = sorted({str(c.manifest_path) for c in all_changes})
        dependencies = sorted({c.dependency_name for c in all_changes})
        triggers = sorted(
            {
                p.target.package_name or p.target.root.name
                for p in plan.packages
            }
        )

        extra = build_hook_env(
            event="dependencies_autoupdated",
            repo_root=plan.repo_root,
            dry_run=False,
            tag_names=plan.tag_names,
            dependency_update_count=len(all_changes),
            dependency_update_projects=projects,
            dependency_update_files=files,
            dependency_update_dependencies=dependencies,
            dependency_update_triggers=triggers,
        )
        run_hook_specs(
            specs,
            repo_root=plan.repo_root,
            extra_env=extra,
        )

    def _commit_release(
        self,
        plan: ReleasePlan,
        git: GitRepository,
        dependency_results: list[DependencyUpdateResult],
    ) -> str:
        """Create a release commit or keep HEAD when nothing changed on disk.

        Args:
            plan: Active release plan.
            git: Repository handle for the same repo_root as the plan.
            dependency_results: Dependency autoupdate results (for logging).
        """
        if (
            plan.has_manifest_updates
            or plan.has_changelog_updates
            or git.has_changes_to_commit()
        ):
            log.info("Committing release changes")
            return git.commit_all(plan.commit_message)

        log.debug("No release file changes; skipping commit")

        return git.rev_parse("HEAD")

    def _create_tags(self, plan: ReleasePlan, git: GitRepository) -> None:
        """Create annotated tags for every planned tag name.

        Args:
            plan: Active release plan.
            git: Repository handle for the same repo_root as the plan.
        """
        tag_messages = build_tag_messages(plan.packages)
        for tag_name in plan.tag_names:
            message = tag_messages.get(tag_name, f"Release {tag_name}")
            log.info("Creating tag %s", tag_name)
            git.create_tag(tag_name, message=message)

    def _push_release(
        self,
        plan: ReleasePlan,
        git: GitRepository,
        pushed_out: list[str],
    ) -> None:
        """Push the current branch and release tags to each configured remote.

        Args:
            plan: Active release plan.
            git: Repository handle for the same repo_root as the plan.
            pushed_out: List mutated in place with each remote that fully
                finishes branch and tag pushes (partial progress on errors).
        """
        branch = git.get_current_branch()

        for remote in plan.remotes:
            log.info("Pushing branch %s to %s", branch, remote)
            git.push_branch(remote, branch)
            log.info("Pushing tags to %s", remote)
            git.push_tags(remote, plan.tag_names)
            pushed_out.append(remote)

    def _dry_run_result(
        self, plan: ReleasePlan, config: ResolvedConfig
    ) -> ReleaseResult:
        """Build a successful result describing actions that would run.

        Args:
            plan: Dry-run release plan.
            config: Effective merged configuration.
        """
        dependency_results: list[DependencyUpdateResult] = []

        if config.dependency_updates.enabled:
            request = self._build_dependency_update_request(plan, config)
            request = attrs.evolve(request, dry_run=True)
            dependency_results = run_dependency_updates(request, self.registry)
            self._log_dependency_update_results(dependency_results)

        log.info("[dry-run] Would create tags: %s", plan.tag_names)
        log.info("[dry-run] Would push to remotes: %s", plan.remotes)
        for pkg_plan in plan.packages:
            if pkg_plan.update_manifest:
                log.info(
                    "[dry-run] Would update manifest %s to %s",
                    pkg_plan.target.manifest_path,
                    str(pkg_plan.resolved_version.next),
                )

            update_plan = pkg_plan.changelog_update

            if update_plan is None:
                continue

            log.info("[dry-run] Would update changelog %s", update_plan.path)

            log.log(
                1,
                "[dry-run] Changelog entry preview:\n%s",
                render_inserted_entry_preview(update_plan),
            )
        return ReleaseResult(
            success=True,
            dry_run=True,
            tag_names=plan.tag_names,
            dependency_updates=dependency_results,
        )
