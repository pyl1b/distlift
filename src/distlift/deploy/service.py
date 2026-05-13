"""Plan and execute deploy marker tags."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language, ReleaseMode, ResolvedConfig
from distlift.deploy.index_check import (
    assert_javascript_version_on_registry,
    assert_python_version_on_index,
    javascript_package_name_and_version,
    python_distribution_name_and_version,
)
from distlift.deploy.models import (
    DeployPackageCheck,
    DeployRequest,
    DeployResult,
)
from distlift.deploy.tags import next_deploy_tag_name
from distlift.errors import DeployError, GitStateError
from distlift.logging_utils import get_logger
from distlift.monorepo.discovery import load_managed_packages
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.plugins.registry import PluginRegistry
from distlift.release.models import ReleaseTarget
from distlift.release.monorepo import discover_managed_targets
from distlift.release.simple import prepare_simple_target
from distlift.vcs.git import GitRepository

log = get_logger(__name__)


def _default_registry_for_config(config: ResolvedConfig) -> PluginRegistry:
    """Build the plugin registry from resolved plugin settings.

    Args:
        config: Resolved configuration supplying plugin discovery options.

    Returns:
        A new ``PluginRegistry`` matching ``DistliftApplication._default_registry``.
    """
    manager = PluginManager()

    request = PluginLoadRequest(
        plugin_paths=[Path(p) for p in config.plugins.paths],
        plugin_directories=[Path(d) for d in config.plugins.directories],
        disable_environment_plugins=not config.plugins.enable_environment,
        disable_builtin_plugins=not config.plugins.enable_builtin,
        allow_plugin_override=config.plugins.allow_override,
    )

    return manager.build_registry(request)


def collect_deploy_targets(
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> list[ReleaseTarget]:
    """Resolve deploy targets for simple or monorepo mode.

    Args:
        repo_root: Absolute repository root.
        config: Effective configuration.
        registry: Plugin registry for adapters.
    """
    root = repo_root

    if config.mode == ReleaseMode.MONOREPO:
        packages = load_managed_packages(config)

        return discover_managed_targets(packages, root, config, registry)

    return [prepare_simple_target(root, config, registry)]


def _effective_tag_prefix(request: DeployRequest) -> str:
    """Return CLI override or configured deploy tag prefix.

    Args:
        request: Active deploy request.
    """
    if request.tag_prefix is not None and str(request.tag_prefix).strip():
        return str(request.tag_prefix).strip()

    return request.config.deploy.tag_prefix


def _effective_verify_indexes(request: DeployRequest) -> bool:
    """Return whether registry verification should run.

    Args:
        request: Active deploy request.
    """
    if request.verify_indexes is not None:
        return request.verify_indexes

    return request.config.deploy.verify_indexes


def _verify_targets(
    targets: list[ReleaseTarget],
) -> list[DeployPackageCheck]:
    """Run index checks for every target; return per-target rows.

    Args:
        targets: Package roots to verify at their manifest versions.

    Raises:
        DeployError: When a check fails with no partial row desired (unused —
            we return rows with ok=False instead).
    """
    checks: list[DeployPackageCheck] = []

    for target in targets:
        label = target.package_name or target.root.name
        reg_name = ""
        version = ""

        try:
            if target.language == Language.PYTHON:
                reg_name, version = python_distribution_name_and_version(
                    target.manifest_path,
                    target.root,
                )
                assert_python_version_on_index(reg_name, version)
            elif target.language == Language.JAVASCRIPT:
                reg_name, version = javascript_package_name_and_version(
                    target.manifest_path,
                    target.root,
                )
                assert_javascript_version_on_registry(reg_name, version)
            else:
                raise DeployError(
                    f"verify_indexes does not support language {target.language.value}"
                )

            checks.append(
                DeployPackageCheck(
                    label=label,
                    language=target.language,
                    registry_name=reg_name,
                    version=version,
                    ok=True,
                )
            )

        except DeployError as exc:
            checks.append(
                DeployPackageCheck(
                    label=label,
                    language=target.language,
                    registry_name=reg_name or "(unknown)",
                    version=version or "(unknown)",
                    ok=False,
                    detail=str(exc),
                )
            )

    return checks


def run_deploy(
    request: DeployRequest,
    registry: PluginRegistry | None = None,
) -> DeployResult:
    """Create and push the next ``{prefix}_{N}`` tag at ``HEAD``.

    Args:
        request: Repository, config, dry-run, and optional overrides.
        registry: Optional pre-built plugin registry.

    Returns:
        ``DeployResult`` describing tags, pushes, verification, or errors.
    """
    root = request.repo_root.resolve()

    if registry is None:
        registry = _default_registry_for_config(request.config)

    git = GitRepository(root=root)

    try:
        git.ensure_clean_worktree()
    except GitStateError as exc:
        return DeployResult(
            success=False,
            dry_run=request.dry_run,
            error=str(exc),
        )

    prefix = _effective_tag_prefix(request)

    try:
        tag_name = next_deploy_tag_name(git.get_tags(), prefix)
    except Exception as exc:
        log.error("Failed to compute deploy tag name: %s", exc, exc_info=True)

        return DeployResult(
            success=False,
            dry_run=request.dry_run,
            error=str(exc),
        )

    checks: list[DeployPackageCheck] = []

    if _effective_verify_indexes(request):
        targets = collect_deploy_targets(root, request.config, registry)
        checks = _verify_targets(targets)
        failures = [c for c in checks if not c.ok]

        if failures:
            msg = "; ".join(
                "{}: {}".format(f.label, f.detail or "index check failed")
                for f in failures
            )

            return DeployResult(
                success=False,
                dry_run=request.dry_run,
                tag_name=tag_name,
                checks=checks,
                error=msg,
            )

    if request.dry_run:
        log.info("[dry-run] Would create tag %s", tag_name)
        log.info(
            "[dry-run] Would push tag to remotes: %s", request.config.remotes
        )

        return DeployResult(
            success=True,
            dry_run=True,
            tag_name=tag_name,
            checks=checks,
        )

    message = f"Deploy marker {tag_name}"

    try:
        git.create_tag(tag_name, message=message)
    except GitStateError as exc:
        return DeployResult(
            success=False,
            dry_run=False,
            tag_name=tag_name,
            checks=checks,
            error=str(exc),
        )

    pushed: list[str] = []

    try:
        for remote in request.config.remotes:
            log.info("Pushing tag %s to %s", tag_name, remote)
            git.push_tag(remote, tag_name)
            pushed.append(remote)
    except GitStateError as exc:
        return DeployResult(
            success=False,
            dry_run=False,
            tag_name=tag_name,
            pushed_remotes=pushed,
            checks=checks,
            error=str(exc),
        )

    return DeployResult(
        success=True,
        dry_run=False,
        tag_name=tag_name,
        pushed_remotes=pushed,
        checks=checks,
    )
