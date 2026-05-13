"""Application facade wiring configuration, plugins, release, and publish."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.loader import load_config_layers
from distlift.config.merger import merge_config_layers
from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.monorepo.discovery import load_managed_packages
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.plugins.registry import PluginRegistry
from distlift.publish.models import (
    BuildArtifact,
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


def _collect_artifacts_for_target(
    target: ReleaseTarget,
    package_manager: str = "npm",
) -> list[BuildArtifact]:
    """Build local distribution artifacts for the given release target.

    Args:
        target: Resolved project root and language.
        package_manager: Package manager string (``npm``, ``pnpm``, or
            ``yarn``) for JavaScript projects.

    Returns:
        Built artifacts returned by the language-specific builder.
    """
    from distlift.publish.javascript import build_javascript_distributions
    from distlift.publish.python import build_python_distributions

    root = target.root

    # Dispatch to the Python builder when the target is a Python project
    if target.language == Language.PYTHON:
        return build_python_distributions(root)

    # Dispatch to the JavaScript builder when the target is a JS project
    if target.language == Language.JAVASCRIPT:
        return build_javascript_distributions(
            root, package_manager=package_manager
        )

    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"Cannot build: unsupported language {target.language.value}"
    )


def _build_target_only(
    target: ReleaseTarget,
    package_manager: str = "npm",
) -> PublishResult:
    """Build artifacts for ``target`` without uploading them.

    Args:
        target: Resolved project root and language.
        package_manager: Package manager string for JavaScript projects.

    Returns:
        A successful result carrying the produced artifacts.
    """
    artifacts = _collect_artifacts_for_target(target, package_manager)
    return PublishResult(success=True, artifacts=list(artifacts))


def _build_and_publish_target(
    target: ReleaseTarget,
    dry_run: bool,
    package_manager: str = "npm",
) -> PublishResult:
    """Build artifacts for ``target`` and run the language publisher.

    Args:
        target: Resolved project root and language.
        dry_run: When ``True``, uploads are skipped by the publisher
            implementations.
        package_manager: Package manager string for JavaScript projects.

    Returns:
        Result of the publish step for the built artifacts.
    """
    from distlift.publish.javascript import publish_javascript_distributions
    from distlift.publish.python import publish_python_distributions

    artifacts = _collect_artifacts_for_target(target, package_manager)
    request = PublishRequest(artifacts=artifacts, dry_run=dry_run)

    # Route the publish request to the Python publisher implementation
    if target.language == Language.PYTHON:
        return publish_python_distributions(request)

    # Route the publish request to the JavaScript publisher implementation
    if target.language == Language.JAVASCRIPT:
        return publish_javascript_distributions(
            request, package_manager=package_manager
        )

    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"Cannot publish: unsupported language {target.language.value}"
    )


@attrs.define
class DistliftApplication:
    """Coordinates config loading, plugin setup, releases, and publishing.

    Instances are stateless facades; they do not hold mutable run state beyond
    what callers pass into each method.

    Attributes:
        None
    """

    def run_default_command(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        *,
        dry_run: bool,
        build: bool,
        publish: bool,
        registry: PluginRegistry | None = None,
    ) -> tuple[ReleaseResult, PublishRunResult | None]:
        """Run patch release plus optional artifact build or publish.

        Simple mode bumps the patch level. Monorepo mode uses the same
        selection rules as ``distlift release monorepo`` without
        ``--all-changed`` or ``--package`` (every managed package is included).

        Args:
            repo_root: Repository root directory path.
            config: Effective merged ``ResolvedConfig`` for this run.
            dry_run: When ``True``, skips release Git writes and registry
                uploads according to each step's semantics.
            build: When ``True``, build distributions after a successful
                release.
            publish: When ``True``, build and upload after a successful
                release.
            registry: Optional pre-built ``PluginRegistry``; when omitted, a
                default registry is built from ``config``.

        Returns:
            Release outcome, then build/publish aggregate when requested, else
            ``None`` for the second element.
        """
        # Resolve a registry once for both release and optional publish steps
        if registry is None:
            registry = self._default_registry(config)

        root = repo_root.resolve()

        # Branch between monorepo and simple release planning and execution
        if config.mode == ReleaseMode.MONOREPO:
            monorepo_req = MonorepoReleaseRequest(
                repo_root=root,
                config=config,
                default_bump=BumpKind.PATCH,
                selected_packages=[],
                all_changed=False,
                dry_run=dry_run,
            )
            release_result = self.run_monorepo_release(
                monorepo_req, registry=registry
            )
        else:
            simple_req = SimpleReleaseRequest(
                repo_root=root,
                config=config,
                bump=BumpKind.PATCH,
                explicit_version=None,
                dry_run=dry_run,
            )
            release_result = self.run_simple_release(
                simple_req, registry=registry
            )

        if not release_result.success:
            return release_result, None

        optional: PublishRunResult | None = None

        # Optional distribution build or publish after tagging
        if build or publish:
            optional = self._run_optional_build_publish(
                root,
                config,
                dry_run,
                build,
                publish,
                registry=registry,
            )

        return release_result, optional

    def _run_optional_build_publish(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        dry_run: bool,
        build: bool,
        publish: bool,
        *,
        registry: PluginRegistry,
    ) -> PublishRunResult:
        """Build and optionally publish per targeted package root.

        Args:
            repo_root: Resolved repository root directory path.
            config: Effective merged ``ResolvedConfig`` for this run.
            dry_run: Passed through to publishers when ``publish`` is
                ``True``.
            build: When ``True`` and ``publish`` is ``False``, build only per
                project.
            publish: When ``True``, build and invoke the registry publisher.
            registry: Loaded plugin registry (must match release planning).

        Returns:
            One result row per targeted package or project root.
        """
        projects_out: list[tuple[str, PublishResult]] = []

        if config.mode == ReleaseMode.MONOREPO:
            # One cycle per declared monorepo package
            for pkg in load_managed_packages(config):
                pkg_root = (repo_root / pkg.path).resolve()
                pkg_config = (
                    attrs.evolve(config, language=pkg.language)
                    if pkg.language is not None
                    else config
                )
                target = prepare_simple_target(pkg_root, pkg_config, registry)

                # Either publish (build+upload) or build-only per package
                if publish:
                    pr = _build_and_publish_target(target, dry_run)
                else:
                    pr = _build_target_only(target)
                projects_out.append((pkg.name, pr))

        else:
            target = prepare_simple_target(repo_root, config, registry)
            label = target.package_name or repo_root.name

            if publish:
                pr = _build_and_publish_target(target, dry_run)
            else:
                pr = _build_target_only(target)
            projects_out.append((label, pr))

        success = all(pr.success for _, pr in projects_out)

        return PublishRunResult(success=success, projects=projects_out)

    def run_simple_release(
        self,
        request: SimpleReleaseRequest,
        registry: PluginRegistry | None = None,
    ) -> ReleaseResult:
        """Plan and execute a simple (single-package) release.

        Args:
            request: Simple release request with repo root, bump, and flags.
            registry: Optional ``PluginRegistry``; when omitted, one is built
                from ``request.config``.

        Returns:
            ``ReleaseResult`` describing success, tags, pushes, or error text.
        """
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
        """Plan and execute a monorepo release for the requested packages.

        Args:
            request: Monorepo release request with selection and bump defaults.
            registry: Optional ``PluginRegistry``; when omitted, one is built
                from ``request.config``.

        Returns:
            ``ReleaseResult`` describing success, tags, pushes, or error text.
        """
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
        """Build distributions and invoke the publisher for each package root.

        In monorepo mode, every declared package root is published in sequence.

        Args:
            repo_root: Repository root containing the workspace.
            config: Resolved effective configuration.
            dry_run: When ``True``, upload steps honor per-language dry-run
                semantics.
            registry: Optional pre-built ``PluginRegistry``.

        Returns:
            Aggregated outcomes; ``error`` is set when setup fails before
            publish.
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
        """Load and merge configuration layers for a repository.

        Args:
            repo_root: Repository root used to locate standard config files.
            extra_config_paths: Optional additional TOML paths merged in order
                after discovered layers.

        Returns:
            Fully merged ``ResolvedConfig`` for downstream release logic.
        """
        layers = load_config_layers(
            repo_root=repo_root,
            extra_paths=extra_config_paths,
        )
        config = merge_config_layers(layers)
        return config

    def load_plugins(self, config: ResolvedConfig) -> PluginRegistry:
        """Build the default plugin registry described by ``config``.

        Args:
            config: Resolved configuration containing plugin paths and flags.

        Returns:
            A ``PluginRegistry`` with built-in and discovered plugins loaded.
        """
        return self._default_registry(config)

    def _default_registry(self, config: ResolvedConfig) -> PluginRegistry:
        """Construct the plugin registry from resolved plugin settings.

        Args:
            config: Resolved configuration supplying plugin discovery options.

        Returns:
            A new ``PluginRegistry`` built for this configuration snapshot.
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
