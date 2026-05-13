from __future__ import annotations

import attrs

from distlift.changelog.builder import render_inserted_entry_preview
from distlift.changelog.writer import write_changelog_document
from distlift.config.models import Language, ResolvedConfig
from distlift.errors import HookExecutionError
from distlift.hooks import build_hook_env, run_hook_specs, specs_for_event
from distlift.languages.base import ProjectAdapter
from distlift.logging_utils import get_logger
from distlift.plugins.registry import PluginRegistry
from distlift.release.models import ReleasePlan, ReleaseResult
from distlift.release.planner import build_tag_messages
from distlift.vcs.git import GitRepository

log = get_logger(__name__)


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
            return self._dry_run_result(plan)

        git = GitRepository(root=plan.repo_root)
        push_failed = False
        commit_sha: str | None = None
        pushed_remotes: list[str] = []

        try:
            self._apply_changelog_updates(plan)
            self._apply_manifest_updates(plan)
            commit_sha = self._commit_release(plan, git)
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

                    log.error(
                        "Release execution failed: %s",
                        exc,
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

            log.error(
                "Release execution failed: %s",
                exc,
                exc_info=True,
            )

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

    def _commit_release(self, plan: ReleasePlan, git: GitRepository) -> str:
        """Create a release commit or keep HEAD when manifests are unchanged.

        Args:
            plan: Active release plan.
            git: Repository handle for the same repo_root as the plan.
        """
        if plan.has_manifest_updates or plan.has_changelog_updates:
            log.info("Committing release changes")
            return git.commit_all(plan.commit_message)

        log.debug("No manifest or changelog updates; skipping commit")

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
                finishes branch and tag pushes (for partial progress on errors).
        """
        branch = git.get_current_branch()

        for remote in plan.remotes:
            log.info("Pushing branch %s to %s", branch, remote)
            git.push_branch(remote, branch)
            log.info("Pushing tags to %s", remote)
            git.push_tags(remote, plan.tag_names)
            pushed_out.append(remote)

    def _dry_run_result(self, plan: ReleasePlan) -> ReleaseResult:
        """Build a successful result describing actions that would run.

        Args:
            plan: Dry-run release plan.
        """
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
        )
