from __future__ import annotations

from pathlib import Path

import attrs as _attrs

from distlift.config.models import Language, ResolvedConfig
from distlift.errors import UnsupportedLanguageError
from distlift.languages.base import ProjectAdapter
from distlift.plugins.registry import PluginRegistry
from distlift.release.changelog_extra import finalize_plan_with_changelog
from distlift.release.models import (
    ReleasePlan,
    ReleaseTarget,
    SimpleReleaseRequest,
)
from distlift.release.planner import plan_simple_release
from distlift.vcs.git import GitRepository
from distlift.versioning.resolver import (
    resolve_current_version,
    resolve_next_version,
)


def _get_adapter(
    registry: PluginRegistry, language: Language
) -> ProjectAdapter:
    """Return a project adapter for the registered language plugin.

    Args:
        registry: Active plugin registry.
        language: Language enum member to resolve.
    """
    plugin = registry.get_language_plugin(language.value)
    from distlift.languages.javascript import JavaScriptProjectPlugin
    from distlift.languages.python import PythonProjectPlugin

    if isinstance(plugin, PythonProjectPlugin):
        from distlift.languages.python import PythonProjectAdapter

        return PythonProjectAdapter()
    if isinstance(plugin, JavaScriptProjectPlugin):
        from distlift.languages.javascript import JavaScriptProjectAdapter

        return JavaScriptProjectAdapter()
    raise UnsupportedLanguageError(
        f"No adapter for language plugin: {plugin.get_name()}"
    )


def prepare_simple_target(
    root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> ReleaseTarget:
    """Resolve language (if needed) and build the simple-mode release target.

    Args:
        root: Repository root used for project detection.
        config: Resolved configuration; language may be auto-detected.
        registry: Plugin registry for language plugins and adapters.
    """
    if config.language is None:
        # Try each registered language until one detects a matching project
        for lang in Language:
            plugin = (
                registry.get_language_plugin(lang.value)
                if registry.has_language(lang.value)
                else None
            )
            if plugin is None:
                continue
            adapter = _get_adapter(registry, lang)
            if adapter.detect_project(root):
                config = _attrs.evolve(config, language=lang)
                break
        if config.language is None:
            raise UnsupportedLanguageError(
                "Cannot detect project language; specify --language"
            )

    adapter = _get_adapter(registry, config.language)
    return adapter.load_release_target(root, config)


def compute_simple_release_plan(
    request: SimpleReleaseRequest,
    registry: PluginRegistry,
) -> ReleasePlan:
    """Compute a simple-mode plan: clean tree, resolve versions, build plan.

    Args:
        request: Repo root, config, bump or explicit version, dry-run flag.
        registry: Plugin registry used when preparing the release target.
    """
    git = GitRepository(root=request.repo_root)
    git.ensure_clean_worktree()

    target = prepare_simple_target(request.repo_root, request.config, registry)
    tags = git.get_tags()

    current = resolve_current_version(
        tags=tags,
        template=request.config.tag_template,
        fmt=request.config.version_format,
        default_version=request.config.default_version,
        package_name=target.package_name,
    )

    resolved = resolve_next_version(
        current=current,
        bump=request.bump,
        explicit=request.explicit_version,
        fmt=request.config.version_format,
        template=request.config.tag_template,
        package_name=target.package_name,
    )

    plan = plan_simple_release(
        target, resolved, request.config, request.dry_run
    )

    plan = finalize_plan_with_changelog(
        plan,
        git_repo=git,
        tags=tags,
        config=request.config,
        skip_changelog=request.skip_changelog,
    )

    return _attrs.evolve(
        plan,
        changelog_prompt_editor=request.config.changelog.prompt_editor,
        skip_changelog_editor=request.skip_changelog_editor,
        editor_command=request.config.editor,
    )
