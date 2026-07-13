"""Concurrent registry version resolution with caching."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencyVersionChoice,
    PackageSource,
    RegistryVersion,
)
from distlift.dependencies.version_cycle import latest_stable_version
from distlift.logging_utils import get_logger
from distlift.plugins.base import PackageManagerPlugin

log = get_logger(__name__)


class RegistryResolver:
    """Fetch and cache registry versions for dependency rows.

    Attributes:
        _registry: Plugin registry providing package manager plugins.
        _plugin: Package manager plugin serving one source.
        _timeout_seconds: Registry subprocess timeout.
        _max_workers: Concurrent fetch worker count.
        _cache: Cached registry responses keyed by package name.
    """

    def __init__(
        self,
        plugin: PackageManagerPlugin,
        *,
        timeout_seconds: int,
        max_workers: int,
    ) -> None:
        self._plugin = plugin
        self._timeout_seconds = timeout_seconds
        self._max_workers = max_workers
        self._cache: dict[str, list[RegistryVersion]] = {}

    def build_choices(
        self,
        source: PackageSource,
        dependencies: list[DeclaredDependency],
    ) -> list[DependencyVersionChoice]:
        """Resolve registry data for each dependency in deterministic order.

        Args:
            source: Package source providing registry context.
            dependencies: Declared dependencies to resolve.
        """
        sorted_deps = sorted(
            dependencies,
            key=lambda dep: (dep.group, dep.name.lower()),
        )
        choices: list[DependencyVersionChoice] = []

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    self._resolve_one,
                    source,
                    dep,
                ): dep
                for dep in sorted_deps
            }

            by_name: dict[str, DependencyVersionChoice] = {}

            for future in as_completed(futures):
                dep = futures[future]

                try:
                    choice = future.result()
                except Exception as exc:
                    log.log(
                        1,
                        "Registry lookup failed for %s: %s",
                        dep.name,
                        exc,
                        exc_info=True,
                    )
                    choice = DependencyVersionChoice(
                        dependency=dep,
                        lookup_error=str(exc),
                    )

                by_name[dep.location_key] = choice

        for dep in sorted_deps:
            choices.append(by_name[dep.location_key])

        return choices

    def _resolve_one(
        self,
        source: PackageSource,
        dependency: DeclaredDependency,
    ) -> DependencyVersionChoice:
        """Resolve registry versions for one dependency.

        Args:
            source: Package source providing registry context.
            dependency: Declared dependency to query.
        """
        if dependency.is_workspace:
            return DependencyVersionChoice(
                dependency=dependency,
                lookup_error="workspace dependencies are not upgradable in v1",
            )

        if dependency.name in self._cache:
            versions = self._cache[dependency.name]
        else:
            versions = self._plugin.fetch_available_versions(
                dependency.name,
                source,
                timeout_seconds=self._timeout_seconds,
            )
            self._cache[dependency.name] = versions

        stable = latest_stable_version(tuple(versions))

        return DependencyVersionChoice(
            dependency=dependency,
            available_versions=tuple(versions),
            latest_stable=stable,
        )


def enrich_dependency_metadata(
    plugin: PackageManagerPlugin,
    source: PackageSource,
    dependencies: list[DeclaredDependency],
) -> list[DeclaredDependency]:
    """Return dependencies enriched with lock and installed versions.

    Args:
        plugin: Package manager plugin for the source.
        source: Package source being inspected.
        dependencies: Declared dependencies from inventory.
    """
    lock_versions = plugin.read_lock_versions(source)
    installed_versions = plugin.read_installed_versions(source)
    enriched: list[DeclaredDependency] = []

    for dep in dependencies:
        enriched.append(
            DeclaredDependency(
                name=dep.name,
                group=dep.group,
                constraint=dep.constraint,
                location_key=dep.location_key,
                resolved_version=lock_versions.get(dep.name),
                installed_version=installed_versions.get(dep.name),
                is_workspace=dep.is_workspace,
            )
        )

    return enriched
