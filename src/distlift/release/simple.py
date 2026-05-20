from __future__ import annotations

from pathlib import Path

import attrs as _attrs

from distlift.config.models import Language, ResolvedConfig, VersionSource
from distlift.errors import UnsupportedLanguageError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.handler import get_handler, kind_for_language
from distlift.plugins.registry import PluginRegistry
from distlift.release.changelog_extra import finalize_plan_with_changelog
from distlift.release.models import (
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
    ResolvedVersionFile,
    SimpleReleaseRequest,
)
from distlift.release.planner import plan_simple_release
from distlift.release.version_files import (
    primary_version_file,
    resolve_version_files,
    validate_version_files,
)
from distlift.vcs.git import GitRepository
from distlift.versioning.bump import coerce_initial_version
from distlift.versioning.models import VersionParts
from distlift.versioning.parser import parse_version
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


def _current_from_manifest(
    primary: ResolvedVersionFile,
    default_version: str,
    fmt: object,
) -> VersionParts:
    """Read the current version from the primary manifest file.

    Args:
        primary: Primary version file to read from.
        default_version: Fallback when no version is declared.
        fmt: Version format for coercion of the default version.
    """
    from distlift.config.models import VersionFormat

    assert isinstance(fmt, VersionFormat)
    handler = get_handler(primary.kind)

    if handler is None:
        return coerce_initial_version(default_version, fmt)

    raw = handler.read_version(primary.path)

    if raw:
        return parse_version(raw, fmt)

    return coerce_initial_version(default_version, fmt)


def _is_dynamic_via_files(
    files: list[ResolvedVersionFile],
) -> bool:
    """Return True when the primary manifest file uses a dynamic version.

    Args:
        files: Resolved version files for the release unit.
    """
    primary = primary_version_file(files)

    if primary is None:
        return False

    handler = get_handler(primary.kind)

    if handler is None:
        return False

    return handler.is_dynamic(primary.path)


def _build_version_files_to_update(
    files: list[ResolvedVersionFile],
) -> list[ResolvedVersionFile]:
    """Return only those files that should be written.

    Args:
        files: Resolved version files for the release unit.
    """
    return [f for f in files if f.update and not _file_is_dynamic(f)]


def _file_is_dynamic(f: ResolvedVersionFile) -> bool:
    """Return True when the file's handler reports a dynamic version.

    Args:
        f: Resolved version file to check.
    """
    handler = get_handler(f.kind)
    if handler is None:
        return False
    return handler.is_dynamic(f.path)


def prepare_simple_target(
    root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> tuple[ReleaseTarget, list[ResolvedVersionFile]]:
    """Resolve language (if needed) and build the simple-mode release target.

    Returns the target and the resolved version files (may be empty for the
    legacy path).

    Args:
        root: Repository root used for project detection.
        config: Resolved configuration; language may be auto-detected.
        registry: Plugin registry for language plugins and adapters.
    """
    # New path: explicit version_files in config
    if config.version_files:
        resolved = resolve_version_files(config.version_files, root)
        validate_version_files(resolved, config.version_source, "simple")

        # Determine language from primary file's kind when not set in config
        language = config.language
        if language is None:
            pf = primary_version_file(resolved)
            if pf is not None:
                for lang in Language:
                    if kind_for_language(str(lang)) == pf.kind:
                        language = lang
                        break

        # Determine manifest_path for legacy compat (primary file)
        pf = primary_version_file(resolved)
        manifest = pf.path if pf else None

        target = ReleaseTarget(
            language=language,
            root=root,
            manifest_path=manifest,
            version_source=config.version_source,
            version_files=resolved,
        )
        return target, resolved

    # Legacy path: language + manifest_path
    if config.language is None:
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
    target = adapter.load_release_target(root, config)
    return target, []


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

    target, resolved_files = prepare_simple_target(
        request.repo_root, request.config, registry
    )
    tags = git.get_tags()
    config = request.config

    # Version resolution: manifest source reads from primary file
    if config.version_source == VersionSource.MANIFEST and resolved_files:
        primary = primary_version_file(resolved_files)
        if primary is not None:
            current = _current_from_manifest(
                primary,
                config.default_version,
                config.version_format,
            )
        else:
            current = resolve_current_version(
                tags=tags,
                template=config.tag_template,
                fmt=config.version_format,
                default_version=config.default_version,
            )
    else:
        current = resolve_current_version(
            tags=tags,
            template=config.tag_template,
            fmt=config.version_format,
            default_version=config.default_version,
            package_name=target.package_name,
        )

    resolved = resolve_next_version(
        current=current,
        bump=request.bump,
        explicit=request.explicit_version,
        fmt=config.version_format,
        template=config.tag_template,
        package_name=target.package_name,
    )

    # Determine whether manifests are dynamic
    if resolved_files:
        is_dynamic = _is_dynamic_via_files(resolved_files)
    else:
        # Legacy: check via adapter
        if target.language is not None:
            adapter = _get_adapter(registry, target.language)
            is_dynamic = adapter.is_dynamic_version(target)
        else:
            is_dynamic = target.version_source == VersionSource.TAG

    update_manifest = not is_dynamic
    files_to_update = (
        _build_version_files_to_update(resolved_files)
        if resolved_files
        else []
    )

    package_plan = PackageReleasePlan(
        target=target,
        resolved_version=resolved,
        update_manifest=update_manifest,
        version_files_to_update=files_to_update,
    )

    plan = plan_simple_release(
        target, resolved, config, request.dry_run, package_plan=package_plan
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
