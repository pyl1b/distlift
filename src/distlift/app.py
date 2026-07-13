"""Application facade wiring configuration, plugins, release, and publish."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.loader import load_config_layers
from distlift.config.merger import merge_config_layers
from distlift.config.models import (
    BumpKind,
    Language,
    ManagedPackageConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.dependencies.models import (
    DependencyUpdateRequest,
    DependencyUpdateResult,
    ReleasedProjectVersion,
)
from distlift.dependencies.service import run_dependency_updates
from distlift.deploy.models import DeployRequest, DeployResult
from distlift.deploy.service import run_deploy as run_deploy_service
from distlift.errors import ConfigurationError, HookExecutionError
from distlift.hooks import (
    build_hook_env,
    run_config_hooks,
    run_hook_specs,
    specs_for_event,
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

    if target.language == Language.PYTHON:
        return build_python_distributions(root)

    if target.language == Language.JAVASCRIPT:
        return build_javascript_distributions(
            root, package_manager=package_manager
        )

    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"Cannot build: unsupported language {target.language!r}"
    )


def _collect_artifacts_for_ecosystem(
    root: Path,
    ecosystem: str,
    command: str | None = None,
    artifacts_globs: list[str] | None = None,
    package_manager: str = "npm",
) -> list[BuildArtifact]:
    """Build artifacts using an explicit ecosystem string.

    Args:
        root: Directory to run the build in.
        ecosystem: ``"python"``, ``"npm"``, or ``"shell"``.
        command: Shell command used when ecosystem is ``"shell"``.
        artifacts_globs: Glob patterns for shell build outputs.
        package_manager: npm/pnpm/yarn for JavaScript projects.
    """
    from distlift.publish.javascript import build_javascript_distributions
    from distlift.publish.python import build_python_distributions

    if ecosystem == "python":
        return build_python_distributions(root)

    if ecosystem in ("npm", "javascript"):
        return build_javascript_distributions(
            root, package_manager=package_manager
        )

    if ecosystem == "shell":
        import glob as _glob
        import subprocess

        if not command:
            raise ConfigurationError(
                "build target with ecosystem='shell' requires a 'command'"
            )
        subprocess.run(command, shell=True, cwd=root, check=True)
        found: list[BuildArtifact] = []
        for pattern in artifacts_globs or []:
            for match in _glob.glob(str(root / pattern)):
                found.append(BuildArtifact(path=Path(match)))
        return found

    raise ConfigurationError(
        f"Unknown build ecosystem {ecosystem!r}; expected python, npm, or shell"
    )


def _publish_artifacts_for_ecosystem(
    root: Path,
    ecosystem: str,
    artifacts: list[BuildArtifact],
    dry_run: bool,
    package_manager: str = "npm",
) -> PublishResult:
    """Publish already-built artifacts using an explicit ecosystem string.

    Args:
        root: Build root (used for context).
        ecosystem: ``"python"`` or ``"npm"``.
        artifacts: Artifacts to upload.
        dry_run: When True, skip actual uploads.
        package_manager: npm/pnpm/yarn for JavaScript projects.
    """
    from distlift.publish.javascript import publish_javascript_distributions
    from distlift.publish.python import publish_python_distributions

    request = PublishRequest(artifacts=artifacts, dry_run=dry_run)

    if ecosystem == "python":
        return publish_python_distributions(request)

    if ecosystem in ("npm", "javascript"):
        return publish_javascript_distributions(
            request, package_manager=package_manager
        )

    if ecosystem == "shell":
        return PublishResult(success=True, artifacts=list(artifacts))

    raise ConfigurationError(
        f"Unknown publish ecosystem {ecosystem!r}; expected python or npm"
    )


def _publish_built_artifacts(
    target: ReleaseTarget,
    artifacts: list[BuildArtifact],
    dry_run: bool,
    package_manager: str = "npm",
) -> PublishResult:
    """Upload already-built artifacts for ``target`` using its language.

    Args:
        target: Resolved project root and language.
        artifacts: Built files to pass to the publisher CLI.
        dry_run: When ``True``, uploads are skipped.
        package_manager: Package manager string for JavaScript projects.
    """
    from distlift.publish.javascript import publish_javascript_distributions
    from distlift.publish.python import publish_python_distributions

    request = PublishRequest(artifacts=artifacts, dry_run=dry_run)

    if target.language == Language.PYTHON:
        return publish_python_distributions(request)

    if target.language == Language.JAVASCRIPT:
        return publish_javascript_distributions(
            request, package_manager=package_manager
        )

    from distlift.errors import UnsupportedLanguageError

    raise UnsupportedLanguageError(
        f"Cannot publish: unsupported language {target.language!r}"
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
        all_changed: bool = True,
        skip_changelog: bool = False,
        skip_changelog_editor: bool = False,
        bump: BumpKind | None = None,
        explicit_version: str | None = None,
        registry: PluginRegistry | None = None,
    ) -> tuple[ReleaseResult, PublishRunResult | None]:
        """Run release plus optional artifact build or publish.

        With ``bump`` and ``explicit_version`` unset, a **patch** bump is used.
        Otherwise ``explicit_version`` selects an exact next version, or
        ``bump`` selects the semver component to increment.

        Simple mode targets one package. Monorepo mode uses change-detection
        by default (same as ``distlift release monorepo --all-changed``).
        Pass ``all_changed=False`` to release every configured package
        regardless of commits.

        Args:
            repo_root: Repository root directory path.
            config: Effective merged ``ResolvedConfig`` for this run.
            dry_run: When ``True``, skips release Git writes and registry
                uploads according to each step's semantics.
            build: When ``True``, build distributions after a successful
                release.
            publish: When ``True``, build and upload after a successful
                release.
            all_changed: When ``True`` (default), only packages with commits
                since their last tag are released in monorepo mode.  Set to
                ``False`` to release every configured package.
            skip_changelog: When ``True``, skip changelog planning in this
                run.
            skip_changelog_editor: When ``True``, skip interactive changelog
                entry editing before writes.
            bump: Optional bump kind when ``explicit_version`` is unset.
            explicit_version: Optional exact version for the next release.
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

        # Default to patch when the caller passes no version selector
        eff_bump = (
            None if explicit_version is not None else (bump or BumpKind.PATCH)
        )
        eff_explicit = explicit_version

        # Branch between monorepo and simple release planning and execution
        if config.mode == ReleaseMode.MONOREPO:
            monorepo_req = MonorepoReleaseRequest(
                repo_root=root,
                config=config,
                default_bump=eff_bump or BumpKind.PATCH,
                explicit_version=eff_explicit,
                selected_packages=[],
                all_changed=all_changed,
                dry_run=dry_run,
                skip_changelog=skip_changelog,
                skip_changelog_editor=skip_changelog_editor,
            )
            release_result = self.run_monorepo_release(
                monorepo_req, registry=registry
            )
        else:
            simple_req = SimpleReleaseRequest(
                repo_root=root,
                config=config,
                bump=eff_bump,
                explicit_version=eff_explicit,
                dry_run=dry_run,
                skip_changelog=skip_changelog,
                skip_changelog_editor=skip_changelog_editor,
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
                release_tag_names=release_result.tag_names,
                release_commit_sha=release_result.commit_sha,
                monorepo_packages=None,
            )

        return release_result, optional

    def run_local_build(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        *,
        package_names: list[str] | None = None,
        registry: PluginRegistry | None = None,
    ) -> PublishRunResult:
        """Build local distributions from manifests without a release step.

        Uses the version already present in each ``pyproject.toml`` or
        ``package.json``. Does not read Git tags, bump versions, commit, tag,
        push, or upload.

        Args:
            repo_root: Repository root directory path.
            config: Effective merged ``ResolvedConfig``.
            package_names: In monorepo mode, optional non-empty list of
                package ``name`` values to build; every name must exist in
                configuration. When ``None`` or empty, every configured package
                is built. Must be empty or ``None`` in simple mode.
            registry: Optional pre-built ``PluginRegistry``; when omitted, a
                default registry is built from ``config``.

        Returns:
            Aggregated per-package build results and artifact paths.
        """
        # Resolve a registry once for language adapters and builders
        if registry is None:
            registry = self._default_registry(config)

        root = repo_root.resolve()
        names = list(package_names) if package_names else []

        # Reject package filters outside monorepo mode
        if config.mode != ReleaseMode.MONOREPO and names:
            raise ConfigurationError(
                "--package / -p applies only in monorepo mode "
                f"(unknown names: {', '.join(names)})"
            )

        # Resolve which monorepo rows to build when a filter is provided
        monorepo_slice: list[ManagedPackageConfig] | None = None

        if config.mode == ReleaseMode.MONOREPO and names:
            managed = load_managed_packages(config)
            by_name = {pkg.name: pkg for pkg in managed}
            missing = [n for n in names if n not in by_name]

            if missing:
                raise ConfigurationError(
                    f"Unknown monorepo package(s): {', '.join(missing)}"
                )

            # Preserve ``--package`` order; omit duplicate names
            seen: set[str] = set()
            monorepo_slice = []

            for n in names:
                if n not in seen:
                    seen.add(n)
                    monorepo_slice.append(by_name[n])

        return self._run_optional_build_publish(
            root,
            config,
            dry_run=False,
            build=True,
            publish=False,
            registry=registry,
            release_tag_names=None,
            release_commit_sha=None,
            monorepo_packages=monorepo_slice,
        )

    def _build_publish_package_with_hooks(
        self,
        config: ResolvedConfig,
        repo_root: Path,
        target: ReleaseTarget,
        label: str,
        dry_run: bool,
        publish: bool,
        *,
        release_tag_names: list[str] | None,
        release_commit_sha: str | None,
    ) -> PublishResult:
        """Build and optionally publish one project, invoking lifecycle hooks.

        Args:
            config: Effective merged configuration including hooks.
            repo_root: Repository root used as the hook working directory.
            target: Project root and language metadata.
            label: Display name for hooks (package or project).
            dry_run: When True, hooks and registry uploads follow dry-run
                rules.
            publish: When True, upload after a successful build.
            release_tag_names: Tag names from the prior release step, if any.
            release_commit_sha: Release commit hash when the release created
                one.
        """
        package_manager = "npm"

        # Collect build artifacts or record build failure for hooks
        try:
            artifacts = _collect_artifacts_for_target(target, package_manager)
        except Exception as exc:
            if not dry_run:
                try:
                    run_config_hooks(
                        config,
                        "build_failed",
                        repo_root,
                        dry_run=dry_run,
                        package=label,
                        error=str(exc),
                        tag_names=release_tag_names,
                        commit_sha=release_commit_sha,
                    )
                except HookExecutionError as hook_exc:
                    return PublishResult(success=False, error=str(hook_exc))

            return PublishResult(success=False, error=str(exc))

        if not dry_run:
            try:
                run_config_hooks(
                    config,
                    "build_succeeded",
                    repo_root,
                    dry_run=dry_run,
                    package=label,
                    tag_names=release_tag_names,
                    commit_sha=release_commit_sha,
                )
            except HookExecutionError as hook_exc:
                return PublishResult(success=False, error=str(hook_exc))

        if not publish:
            return PublishResult(success=True, artifacts=list(artifacts))

        pr = _publish_built_artifacts(
            target, list(artifacts), dry_run, package_manager
        )

        if not dry_run:
            event = "publish_succeeded" if pr.success else "publish_failed"
            err = None if pr.success else (pr.error or "publish failed")

            try:
                run_config_hooks(
                    config,
                    event,
                    repo_root,
                    dry_run=dry_run,
                    package=label,
                    tag_names=release_tag_names,
                    commit_sha=release_commit_sha,
                    error=err,
                )
            except HookExecutionError as hook_exc:
                return PublishResult(
                    success=False,
                    artifacts=pr.artifacts,
                    error=str(hook_exc),
                )

        return pr

    def _run_optional_build_publish(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        dry_run: bool,
        build: bool,
        publish: bool,
        *,
        registry: PluginRegistry,
        release_tag_names: list[str] | None = None,
        release_commit_sha: str | None = None,
        monorepo_packages: list[ManagedPackageConfig] | None = None,
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
            release_tag_names: Tags created by the release run, if any.
            release_commit_sha: Release commit created by the release run.
            monorepo_packages: When set in monorepo mode, build only these
                managed package rows instead of every configured package.

        Returns:
            One result row per targeted package or project root.
        """
        projects_out: list[tuple[str, PublishResult]] = []

        # Explicit target routing takes priority over language dispatch
        build_targets = config.build.targets if build else []
        publish_targets = config.publish.targets if publish else []

        if build_targets or publish_targets:
            all_target_names = {t.name for t in build_targets} | {
                t.name for t in publish_targets
            }
            for name in sorted(all_target_names):
                bt = next((t for t in build_targets if t.name == name), None)
                pt = next((t for t in publish_targets if t.name == name), None)
                target_path = repo_root / (
                    bt.path if bt else pt.path  # type: ignore[union-attr]
                )
                ecosystem = (bt or pt).ecosystem  # type: ignore[union-attr]

                try:
                    arts = _collect_artifacts_for_ecosystem(
                        target_path.resolve(),
                        ecosystem,
                        command=bt.command if bt else None,
                        artifacts_globs=bt.artifacts if bt else None,
                    )
                except Exception as exc:
                    projects_out.append(
                        (name, PublishResult(success=False, error=str(exc)))
                    )
                    continue

                if not publish or pt is None:
                    projects_out.append(
                        (name, PublishResult(success=True, artifacts=arts))
                    )
                    continue

                pr = _publish_artifacts_for_ecosystem(
                    target_path.resolve(),
                    ecosystem,
                    arts,
                    dry_run,
                )
                projects_out.append((name, pr))

        elif config.mode == ReleaseMode.MONOREPO:
            # One cycle per declared (or caller-selected) monorepo package
            pkg_rows = (
                monorepo_packages
                if monorepo_packages is not None
                else load_managed_packages(config)
            )

            for pkg in pkg_rows:
                pkg_root = (repo_root / pkg.path).resolve()
                pkg_config = (
                    attrs.evolve(config, language=pkg.language)
                    if pkg.language is not None
                    else config
                )
                target, _ = prepare_simple_target(
                    pkg_root, pkg_config, registry
                )

                pr = self._build_publish_package_with_hooks(
                    config,
                    repo_root,
                    target,
                    pkg.name,
                    dry_run,
                    publish,
                    release_tag_names=release_tag_names,
                    release_commit_sha=release_commit_sha,
                )
                projects_out.append((pkg.name, pr))

        else:
            target, _ = prepare_simple_target(repo_root, config, registry)
            label = target.package_name or repo_root.name

            pr = self._build_publish_package_with_hooks(
                config,
                repo_root,
                target,
                label,
                dry_run,
                publish,
                release_tag_names=release_tag_names,
                release_commit_sha=release_commit_sha,
            )
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

            return executor.execute(plan, request.config)
        except Exception as exc:
            from distlift.logging_utils import get_logger

            get_logger(__name__).error("Release planning failed: %s", exc)

            if not request.dry_run:
                try:
                    run_config_hooks(
                        request.config,
                        "release_failed",
                        request.repo_root,
                        dry_run=request.dry_run,
                        error=str(exc),
                    )
                except HookExecutionError as hook_exc:
                    get_logger(__name__).error(
                        "release_failed hook failed: %s",
                        hook_exc,
                        exc_info=True,
                    )
                    return ReleaseResult(
                        success=False,
                        dry_run=request.dry_run,
                        error=str(hook_exc),
                    )

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

            return executor.execute(plan, request.config)
        except Exception as exc:
            from distlift.logging_utils import get_logger

            get_logger(__name__).error(
                "Monorepo release planning failed: %s", exc
            )

            if not request.dry_run:
                try:
                    run_config_hooks(
                        request.config,
                        "release_failed",
                        request.repo_root,
                        dry_run=request.dry_run,
                        error=str(exc),
                    )
                except HookExecutionError as hook_exc:
                    get_logger(__name__).error(
                        "release_failed hook failed: %s",
                        hook_exc,
                        exc_info=True,
                    )
                    return ReleaseResult(
                        success=False,
                        dry_run=request.dry_run,
                        error=str(hook_exc),
                    )

            return ReleaseResult(
                success=False, dry_run=request.dry_run, error=str(exc)
            )

    def run_dependency_autoupdate(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        released: list[ReleasedProjectVersion],
        *,
        dry_run: bool,
        registry: PluginRegistry | None = None,
    ) -> list[DependencyUpdateResult]:
        """Run dependency autoupdate without release planning or Git tagging.

        Args:
            repo_root: Repository root for config and project discovery.
            config: Effective merged configuration.
            released: Released package identities and versions to apply.
            dry_run: When True, report changes without writing files.
            registry: Optional plugin registry; built from config when omitted.

        Returns:
            Dependency update results from built-in and plugin updaters.
        """
        if registry is None:
            registry = self._default_registry(config)

        request = DependencyUpdateRequest(
            repo_root=repo_root.resolve(),
            config=config,
            plan=None,
            released_versions=released,
            dry_run=dry_run,
            run_source="command",
        )
        results = run_dependency_updates(request, registry)

        if dry_run:
            return results

        all_changes = [c for r in results for c in r.changes]

        if not all_changes:
            return results

        specs = specs_for_event(config.hooks, "dependencies_autoupdated")

        if specs:
            projects = sorted({c.project_name for c in all_changes})
            files = sorted({str(c.manifest_path) for c in all_changes})
            dependencies = sorted({c.dependency_name for c in all_changes})
            triggers = sorted(
                {rv.package_name or rv.dependency_name for rv in released}
            )
            extra = build_hook_env(
                event="dependencies_autoupdated",
                repo_root=repo_root.resolve(),
                dry_run=False,
                dependency_update_count=len(all_changes),
                dependency_update_projects=projects,
                dependency_update_files=files,
                dependency_update_dependencies=dependencies,
                dependency_update_triggers=triggers,
            )
            run_hook_specs(
                specs,
                repo_root=repo_root.resolve(),
                extra_env=extra,
            )

        return results

    def run_dependency_upgrade(
        self,
        repo_root: Path,
        config: ResolvedConfig,
        *,
        dry_run: bool = False,
        project_filter: list[str] | None = None,
        manager_overrides: dict[str, str] | None = None,
        selector_backend=None,
        confirm_callback=None,
        registry: PluginRegistry | None = None,
    ):
        """Run the interactive third-party dependency upgrade workflow.

        Args:
            repo_root: Repository root for config and project discovery.
            config: Effective merged configuration.
            dry_run: When True, preview changes without writing files.
            project_filter: Optional project name allow-list.
            manager_overrides: Optional per-project manager overrides.
            selector_backend: Optional injected selector backend for tests.
            confirm_callback: Optional final confirmation callback.
            registry: Optional plugin registry; built from config when omitted.

        Returns:
            Dependency upgrade result with per-source details.
        """
        from distlift.dependencies.upgrade_service import (
            run_interactive_upgrade_session,
        )
        from distlift.terminal.dependency_selector import (
            PromptToolkitSelectorBackend,
        )

        if registry is None:
            registry = self._default_registry(config)

        selector = selector_backend or PromptToolkitSelectorBackend()

        result = run_interactive_upgrade_session(
            repo_root.resolve(),
            config,
            registry,
            dry_run=dry_run,
            selector=selector,
            project_filter=project_filter,
            manager_overrides=manager_overrides,
            confirm_callback=confirm_callback,
        )

        if dry_run or not result.success:
            return result

        all_changes = [
            change
            for source_result in result.source_results
            for change in source_result.manifest_changes
        ]

        if not all_changes:
            return result

        specs = specs_for_event(config.hooks, "dependencies_autoupdated")

        if specs:
            projects = sorted({change.project_name for change in all_changes})
            files = sorted(
                {str(change.manifest_path) for change in all_changes}
            )
            dependencies = sorted(
                {change.dependency_name for change in all_changes}
            )
            extra = build_hook_env(
                event="dependencies_autoupdated",
                repo_root=repo_root.resolve(),
                dry_run=False,
                dependency_update_count=len(all_changes),
                dependency_update_projects=projects,
                dependency_update_files=files,
                dependency_update_dependencies=dependencies,
                dependency_update_triggers=["interactive"],
            )
            run_hook_specs(
                specs,
                repo_root=repo_root.resolve(),
                extra_env=extra,
            )

        return result

    def run_deploy(self, request: DeployRequest) -> DeployResult:
        """Create and push a numbered deploy marker tag at ``HEAD``.

        Args:
            request: Repository root, effective configuration, and dry-run
                flag for this deploy run.

        Returns:
            Outcome with the tag name, remotes pushed to, optional index
            checks, or an error message.
        """
        registry = self._default_registry(request.config)

        return run_deploy_service(request, registry)

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
                    target, _ = prepare_simple_target(
                        pkg_root, pkg_config, registry
                    )
                    pr = self._build_publish_package_with_hooks(
                        config,
                        repo_root.resolve(),
                        target,
                        pkg.name,
                        dry_run,
                        True,
                        release_tag_names=None,
                        release_commit_sha=None,
                    )
                    projects_out.append((pkg.name, pr))

            else:
                target, _ = prepare_simple_target(repo_root, config, registry)
                label = target.package_name or repo_root.resolve().name
                pr = self._build_publish_package_with_hooks(
                    config,
                    repo_root.resolve(),
                    target,
                    label,
                    dry_run,
                    True,
                    release_tag_names=None,
                    release_commit_sha=None,
                )
                projects_out.append((label, pr))

            success = all(pr.success for _, pr in projects_out)
            return PublishRunResult(success=success, projects=projects_out)

        except Exception as exc:
            from distlift.logging_utils import get_logger

            log = get_logger(__name__)
            log.error("Publish failed: %s", exc)

            if not dry_run:
                try:
                    run_config_hooks(
                        config,
                        "release_failed",
                        repo_root.resolve(),
                        dry_run=dry_run,
                        error=str(exc),
                    )
                except HookExecutionError as hook_exc:
                    log.error(
                        "release_failed hook failed: %s",
                        hook_exc,
                        exc_info=True,
                    )
                    return PublishRunResult(success=False, error=str(hook_exc))

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
