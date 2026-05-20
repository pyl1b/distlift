from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    ResolvedConfig,
    VersionSource,
)
from distlift.errors import UnsupportedLanguageError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.handler import get_handler, kind_for_language
from distlift.monorepo.change_detector import (
    find_changed_packages,
)
from distlift.monorepo.discovery import (
    load_managed_packages,
    resolve_package_manifest_path,
)
from distlift.plugins.registry import PluginRegistry
from distlift.release.changelog_extra import finalize_plan_with_changelog
from distlift.release.models import (
    MonorepoReleaseRequest,
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
    ResolvedVersionFile,
)
from distlift.release.planner import plan_monorepo_release
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


def _adapter_for(
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
    raise UnsupportedLanguageError(
        f"No adapter for plugin: {plugin.get_name()}"
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


def _is_dynamic_file(f: ResolvedVersionFile) -> bool:
    handler = get_handler(f.kind)
    return handler.is_dynamic(f.path) if handler else False


def discover_managed_targets(
    packages: list[ManagedPackageConfig],
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> list[tuple[ReleaseTarget, list[ResolvedVersionFile]]]:
    """Build a (ReleaseTarget, resolved_files) pair for each managed package.

    Args:
        packages: Monorepo package entries from configuration.
        repo_root: Repository root used to resolve paths.
        config: Resolved configuration for default language fallbacks.
        registry: Plugin registry (reserved for future per-package wiring).
    """
    result = []

    for pkg in packages:
        pkg_root = repo_root / pkg.path

        # New path: explicit version_files on the package entry
        if pkg.version_files:
            resolved = resolve_version_files(pkg.version_files, pkg_root)
            validate_version_files(resolved, pkg.version_source, pkg.name)

            language = pkg.language or config.language
            if language is None:
                pf = primary_version_file(resolved)
                if pf is not None:
                    for lang in Language:
                        if kind_for_language(str(lang)) == pf.kind:
                            language = lang
                            break

            pf = primary_version_file(resolved)
            manifest = pf.path if pf else None

            target = ReleaseTarget(
                language=language,
                root=pkg_root,
                manifest_path=manifest,
                version_source=pkg.version_source,
                package_name=pkg.name,
                version_files=resolved,
            )
            result.append((target, resolved))
            continue

        # Legacy path: language + manifest_path
        language = pkg.language or config.language
        if language is None:
            raise UnsupportedLanguageError(
                f"Package {pkg.name!r} has no language configured "
                "and no repository default exists"
            )
        manifest = resolve_package_manifest_path(pkg, repo_root)
        target = ReleaseTarget(
            language=language,
            root=pkg_root,
            manifest_path=manifest,
            version_source=pkg.version_source,
            package_name=pkg.name,
        )
        result.append((target, []))

    return result


def select_changed_targets(
    packages: list[ManagedPackageConfig],
    pairs: list[tuple[ReleaseTarget, list[ResolvedVersionFile]]],
    tags: list[str],
    git: GitRepository,
    selected_names: list[str] | None,
    all_changed: bool,
) -> list[
    tuple[ManagedPackageConfig, ReleaseTarget, list[ResolvedVersionFile]]
]:
    """Return (pkg, target, files) triples that should be part of this release.

    Args:
        packages: Declared managed packages in configuration order.
        pairs: Parallel list of (target, resolved_files) for those packages.
        tags: Existing tag names used for change detection.
        git: Repository handle for diff-based change detection.
        selected_names: Optional filter of package names to include.
        all_changed: If True, only packages with commits since their tag.
    """
    if all_changed:
        changed_pkgs = find_changed_packages(
            packages, tags, git, selected_names or None
        )
    else:
        if selected_names:
            changed_pkgs = [p for p in packages if p.name in selected_names]
        else:
            changed_pkgs = list(packages)

    changed_names = {p.name for p in changed_pkgs}
    return [
        (pkg, tgt, files)
        for pkg, (tgt, files) in zip(packages, pairs)
        if pkg.name in changed_names
    ]


def compute_monorepo_release_plan(
    request: MonorepoReleaseRequest,
    registry: PluginRegistry,
) -> ReleasePlan:
    """Compute a monorepo release plan for changed or selected packages.

    Args:
        request: Monorepo request with repo root, bumps, and filters.
        registry: Plugin registry used for adapters and dynamic-version checks.
    """
    git = GitRepository(root=request.repo_root)
    git.ensure_clean_worktree()

    packages = load_managed_packages(request.config)
    pairs = discover_managed_targets(
        packages, request.repo_root, request.config, registry
    )
    tags = git.get_tags()

    selected_names = request.selected_packages or None
    triples = select_changed_targets(
        packages, pairs, tags, git, selected_names, request.all_changed
    )

    pkg_plans: list[PackageReleasePlan] = []

    for pkg, tgt, resolved_files in triples:
        template = pkg.tag_template or f"v{{version}}-{pkg.name}"
        fmt = pkg.version_format

        # Version resolution: manifest source reads from primary file
        if pkg.version_source == VersionSource.MANIFEST and resolved_files:
            pf = primary_version_file(resolved_files)
            if pf is not None:
                current = _current_from_manifest(pf, pkg.default_version, fmt)
            else:
                current = resolve_current_version(
                    tags=tags,
                    template=template,
                    fmt=fmt,
                    default_version=pkg.default_version,
                    package_name=pkg.name,
                )
        else:
            current = resolve_current_version(
                tags=tags,
                template=template,
                fmt=fmt,
                default_version=pkg.default_version,
                package_name=pkg.name,
            )

        resolved = resolve_next_version(
            current=current,
            bump=request.default_bump
            if request.explicit_version is None
            else None,
            explicit=request.explicit_version,
            fmt=fmt,
            template=template,
            package_name=pkg.name,
        )

        # Dynamic-version detection: prefer version-files path
        if resolved_files:
            pf = primary_version_file(resolved_files)
            is_dynamic = _is_dynamic_file(pf) if pf is not None else False
        else:
            adapter = _adapter_for(registry, tgt.language)
            is_dynamic = adapter.is_dynamic_version(tgt)

        update_manifest = not is_dynamic
        files_to_update = (
            [f for f in resolved_files if f.update and not _is_dynamic_file(f)]
            if resolved_files
            else []
        )

        pkg_plans.append(
            PackageReleasePlan(
                target=tgt,
                resolved_version=resolved,
                update_manifest=update_manifest,
                version_files_to_update=files_to_update,
            )
        )

    # Duplicate tag validation
    seen_tags: set[str] = set()
    for pp in pkg_plans:
        tag = pp.resolved_version.tag_name
        if tag in seen_tags:
            raise ValueError(
                f"Duplicate planned tag name {tag!r}. Two packages would "
                "create the same tag — check tag_template settings."
            )
        seen_tags.add(tag)

    plan = plan_monorepo_release(
        pkg_plans, request.config, request.repo_root, request.dry_run
    )

    plan = finalize_plan_with_changelog(
        plan,
        git_repo=git,
        tags=tags,
        config=request.config,
        skip_changelog=request.skip_changelog,
    )

    return attrs.evolve(
        plan,
        changelog_prompt_editor=request.config.changelog.prompt_editor,
        skip_changelog_editor=request.skip_changelog_editor,
        editor_command=request.config.editor,
    )
