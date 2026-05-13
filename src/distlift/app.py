from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.loader import load_config_layers
from distlift.config.merger import merge_config_layers
from distlift.config.models import ResolvedConfig
from distlift.config.validators import validate_resolved_config
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.plugins.registry import PluginRegistry
from distlift.release.executor import ReleaseExecutor
from distlift.release.models import (
    MonorepoReleaseRequest,
    ReleaseResult,
    SimpleReleaseRequest,
)
from distlift.release.monorepo import compute_monorepo_release_plan
from distlift.release.simple import compute_simple_release_plan


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
            return ReleaseResult(success=False, dry_run=request.dry_run, error=str(exc))

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

            get_logger(__name__).error("Monorepo release planning failed: %s", exc)
            return ReleaseResult(success=False, dry_run=request.dry_run, error=str(exc))

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
