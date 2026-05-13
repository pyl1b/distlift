from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.loader import load_config_layers
from distlift.config.merger import merge_config_layers
from distlift.config.models import Language, ReleaseMode, ResolvedConfig
from distlift.monorepo.discovery import load_managed_packages
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.plugins.registry import PluginRegistry
from distlift.publish.models import (
    PublishRequest,
    PublishResult,
    PublishRunResult,
)
from distlift.release.executor import ReleaseExecutor
from distlift.release.models import (
    MonorepoReleaseRequest,
    ReleaseResult,
    ReleaseTarget,
    SimpleReleaseRequest,
)
from distlift.release.monorepo import compute_monorepo_release_plan
from distlift.release.simple import (
    compute_simple_release_plan,
    prepare_simple_target,
)


def _build_and_publish_target(
    target: ReleaseTarget,
    dry_run: bool,
    package_manager: str = "npm",
) -> PublishResult:
    """Build artifacts for ``target`` and run the language publisher.

    Args:
        target: Resolved project root and language.
        dry_run: When True, uploads are skipped by the publisher implementations.
        package_manager: npm, pnpm, or yarn for JavaScript projects.

    Returns:
        Result of the publish step for the built artifacts.
    """
    from distlift.publish.javascript import (
        build_javascript_distributions,
        publish_javascript_distributions,
    )
    from distlift.publish.python import (
        build_python_distributions,
        publish_python_distributions,
    )

    root = target.root

    if target.language == Language.PYTHON:
        artifacts = build_python_distributions(root)
        request = PublishRequest(artifacts=artifacts, dry_run=dry_run)
        return publish_python_distributions(request)

    if target.language == Language.JAVASCRIPT:
        artifacts = build_javascript_distributions(
            root, package_manager=package_manager
        )
        request = PublishRequest(artifacts=artifacts, dry_run=dry_run)
        return publish_javascript_distributions(
            request, package_manager=package_manager
        )

    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"Cannot publish: unsupported language {target.language.value}"
    )


@attrs.define
class DistliftApplication:
    def run_simple_release(
        self,
        request: SimpleReleaseRequest,
        registry: PluginRegistry | None = None,
    ) -> ReleaseResult:
        try:
            if registry is None:
                registry = self._default_registry(request.config)
            plan = compute_simple_release_plan(request, registry)
            executor = ReleaseExecutor(registry=registry)
            return executor.execute(plan)
        except Exception as exc:
            from distlift.logging_utils import get_logger

            get_logger(__name__).error("Release planning failed: %s", exc)
            return ReleaseResult(
                success=False, dry_run=request.dry_run, error=str(exc)
            )

    def run_monorepo_release(
        self,
        request: MonorepoReleaseRequest,
        registry: PluginRegistry | None = None,
    ) -> ReleaseResult:
        try:
            if registry is None:
                registry = self._default_registry(request.config)
            plan = compute_monorepo_release_plan(request, registry)
            executor = ReleaseExecutor(registry=registry)
            return executor.execute(plan)
        except Exception as exc:
            from distlift.logging_utils import get_logger

            get_logger(__name__).error(
                "Monorepo release planning failed: %s", exc
            )
            return ReleaseResult(
                success=False, dry_run=request.dry_run, error=str(exc)
            )

    def run_publish(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        dry_run: bool,
        registry: PluginRegistry | None = None,
    ) -> PublishRunResult:
        """Build distributions and invoke the publisher for each configured package.

        In monorepo mode, every declared package root is published in sequence.

        Args:
            repo_root: Repository root containing the workspace.
            config: Resolved effective configuration.
            dry_run: When True, upload steps honor per-language dry-run semantics.
            registry: Optional pre-built plugin registry.

        Returns:
            Aggregated outcomes; ``error`` is set when setup fails before publish.
        """
        try:
            if registry is None:
                registry = self._default_registry(config)

            projects_out: list[tuple[str, PublishResult]] = []

            if config.mode == ReleaseMode.MONOREPO:
                # One build+publish cycle per declared monorepo package
                for pkg in load_managed_packages(config):
                    pkg_root = (repo_root / pkg.path).resolve()
                    pkg_config = (
                        attrs.evolve(config, language=pkg.language)
                        if pkg.language is not None
                        else config
                    )
                    target = prepare_simple_target(
                        pkg_root, pkg_config, registry
                    )
                    pr = _build_and_publish_target(target, dry_run)
                    projects_out.append((pkg.name, pr))

            else:
                target = prepare_simple_target(repo_root, config, registry)
                label = target.package_name or repo_root.resolve().name
                pr = _build_and_publish_target(target, dry_run)
                projects_out.append((label, pr))

            success = all(pr.success for _, pr in projects_out)
            return PublishRunResult(success=success, projects=projects_out)

        except Exception as exc:
            from distlift.logging_utils import get_logger

            get_logger(__name__).error("Publish failed: %s", exc)
            return PublishRunResult(success=False, error=str(exc))

    def load_effective_config(
        self,
        repo_root: Path,
        extra_config_paths: list[Path] | None = None,
    ) -> ResolvedConfig:
        layers = load_config_layers(
            repo_root=repo_root,
            extra_paths=extra_config_paths,
        )
        config = merge_config_layers(layers)
        return config

    def load_plugins(self, config: ResolvedConfig) -> PluginRegistry:
        return self._default_registry(config)

    def _default_registry(self, config: ResolvedConfig) -> PluginRegistry:
        manager = PluginManager()
        request = PluginLoadRequest(
            plugin_paths=[Path(p) for p in config.plugins.paths],
            plugin_directories=[Path(d) for d in config.plugins.directories],
            disable_environment_plugins=not config.plugins.enable_environment,
            disable_builtin_plugins=not config.plugins.enable_builtin,
            allow_plugin_override=config.plugins.allow_override,
        )
        return manager.build_registry(request)
