from __future__ import annotations

import attrs

from distlift.config.models import Language, VersionSource
from distlift.languages.base import ProjectAdapter
from distlift.logging_utils import get_logger
from distlift.plugins.registry import PluginRegistry
from distlift.release.models import ReleasePlan, ReleaseResult
from distlift.release.planner import build_tag_messages
from distlift.vcs.git import GitRepository

log = get_logger(__name__)


def _get_adapter(registry: PluginRegistry, language: Language) -> ProjectAdapter:
    from distlift.languages.javascript import (
        JavaScriptProjectPlugin,
        JavaScriptProjectAdapter,
    )
    from distlift.languages.python import PythonProjectPlugin, PythonProjectAdapter

    plugin = registry.get_language_plugin(language.value)
    if isinstance(plugin, PythonProjectPlugin):
        return PythonProjectAdapter()
    if isinstance(plugin, JavaScriptProjectPlugin):
        return JavaScriptProjectAdapter()
    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(f"No adapter for plugin: {plugin.get_name()}")


@attrs.define
class ReleaseExecutor:
    registry: PluginRegistry

    def execute(self, plan: ReleasePlan) -> ReleaseResult:
        if plan.dry_run:
            return self._dry_run_result(plan)

        git = GitRepository(root=plan.repo_root)
        try:
            self._apply_manifest_updates(plan)
            commit_sha = self._commit_release(plan, git)
            self._create_tags(plan, git)
            pushed = self._push_release(plan, git)
            return ReleaseResult(
                success=True,
                dry_run=False,
                tag_names=plan.tag_names,
                commit_sha=commit_sha,
                pushed_remotes=pushed,
            )
        except Exception as exc:
            log.error("Release execution failed: %s", exc)
            return ReleaseResult(
                success=False,
                dry_run=False,
                tag_names=[],
                error=str(exc),
            )

    def _apply_manifest_updates(self, plan: ReleasePlan) -> None:
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
        if plan.has_manifest_updates:
            log.info("Committing manifest updates")
            return git.commit_all(plan.commit_message)
        log.debug("No manifest updates; skipping commit")
        return git.rev_parse("HEAD")

    def _create_tags(self, plan: ReleasePlan, git: GitRepository) -> None:
        tag_messages = build_tag_messages(plan.packages)
        for tag_name in plan.tag_names:
            message = tag_messages.get(tag_name, f"Release {tag_name}")
            log.info("Creating tag %s", tag_name)
            git.create_tag(tag_name, message=message)

    def _push_release(self, plan: ReleasePlan, git: GitRepository) -> list[str]:
        branch = git.get_current_branch()
        pushed = []
        for remote in plan.remotes:
            log.info("Pushing branch %s to %s", branch, remote)
            git.push_branch(remote, branch)
            log.info("Pushing tags to %s", remote)
            git.push_tags(remote, plan.tag_names)
            pushed.append(remote)
        return pushed

    def _dry_run_result(self, plan: ReleasePlan) -> ReleaseResult:
        log.info("[dry-run] Would create tags: %s", plan.tag_names)
        log.info("[dry-run] Would push to remotes: %s", plan.remotes)
        for pkg_plan in plan.packages:
            if pkg_plan.update_manifest:
                log.info(
                    "[dry-run] Would update manifest %s to %s",
                    pkg_plan.target.manifest_path,
                    str(pkg_plan.resolved_version.next),
                )
        return ReleaseResult(
            success=True,
            dry_run=True,
            tag_names=plan.tag_names,
        )
