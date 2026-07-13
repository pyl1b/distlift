"""Tests for dependency version cycle helpers."""

from __future__ import annotations

from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencyVersionChoice,
    RegistryVersion,
)
from distlift.dependencies.version_cycle import (
    build_version_cycle,
    currently_used_version,
    filter_upgradable_choices,
    has_available_upgrade,
    latest_stable_version,
    selection_from_cycle_index,
    toggle_stable_or_skip,
)


class TestLatestStableVersion:
    """Tests for latest stable version selection."""

    def test_prefers_non_prerelease(self) -> None:
        versions = (
            RegistryVersion("2.0.0b1", is_prerelease=True),
            RegistryVersion("1.9.0"),
            RegistryVersion("1.8.0"),
        )
        assert latest_stable_version(versions) == "1.9.0"


class TestCurrentlyUsedVersion:
    """Tests for version-cycle baseline resolution."""

    def test_prefers_lock_over_installed(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint=">=1.0.0",
            location_key="k",
            resolved_version="1.2.0",
            installed_version="1.1.0",
        )
        choice = DependencyVersionChoice(dependency=dep)
        assert str(currently_used_version(choice)) == "1.2.0"

    def test_uses_installed_when_lock_missing(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint=">=1.0.0",
            location_key="k",
            installed_version="1.1.0",
        )
        choice = DependencyVersionChoice(dependency=dep)
        assert str(currently_used_version(choice)) == "1.1.0"


class TestBuildVersionCycle:
    """Tests for Space-cycle construction."""

    def test_cycle_includes_skip_and_newer_versions(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint=">=1.0.0",
            location_key="k",
            resolved_version="1.0.0",
        )
        choice = DependencyVersionChoice(
            dependency=dep,
            available_versions=(
                RegistryVersion("2.0.0"),
                RegistryVersion("1.5.0"),
                RegistryVersion("1.0.0"),
            ),
            latest_stable="2.0.0",
        )
        cycle = build_version_cycle(choice)
        assert cycle[0] == "2.0.0"
        assert "1.5.0" in cycle
        assert cycle[-1] is None

    def test_lookup_error_defaults_to_skip_only(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint="^1.0.0",
            location_key="k",
        )
        choice = DependencyVersionChoice(
            dependency=dep,
            lookup_error="failed",
        )
        assert build_version_cycle(choice) == [None]

    def test_cycle_excludes_latest_when_already_installed(self) -> None:
        dep = DeclaredDependency(
            name="attrs",
            group="dependencies",
            constraint="attrs>=23.2",
            location_key="k",
            installed_version="26.1.0",
        )
        choice = DependencyVersionChoice(
            dependency=dep,
            available_versions=(RegistryVersion("26.1.0"),),
            latest_stable="26.1.0",
        )
        assert build_version_cycle(choice) == [None]
        assert not has_available_upgrade(choice)

    def test_filter_upgradable_choices_removes_current_versions(self) -> None:
        current = DeclaredDependency(
            name="attrs",
            group="dependencies",
            constraint="attrs>=23.2",
            location_key="current",
            installed_version="26.1.0",
        )
        newer = DeclaredDependency(
            name="tomlkit",
            group="dependencies",
            constraint="tomlkit>=0.12",
            location_key="newer",
            installed_version="0.12.0",
        )
        choices = [
            DependencyVersionChoice(
                dependency=current,
                available_versions=(RegistryVersion("26.1.0"),),
                latest_stable="26.1.0",
            ),
            DependencyVersionChoice(
                dependency=newer,
                available_versions=(
                    RegistryVersion("0.13.3"),
                    RegistryVersion("0.12.0"),
                ),
                latest_stable="0.13.3",
            ),
        ]
        filtered = filter_upgradable_choices(choices)
        assert [choice.dependency.name for choice in filtered] == ["tomlkit"]


class TestSelectionHelpers:
    """Tests for cycle index helpers."""

    def test_toggle_stable_or_skip(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint="^1.0.0",
            location_key="k",
            resolved_version="1.0.0",
        )
        choice = DependencyVersionChoice(
            dependency=dep,
            available_versions=(RegistryVersion("2.0.0"),),
            latest_stable="2.0.0",
        )
        target, index = toggle_stable_or_skip(choice, 0)
        assert target is None
        target, index = toggle_stable_or_skip(choice, index)
        assert target == "2.0.0"

    def test_selection_from_cycle_index_wraps(self) -> None:
        dep = DeclaredDependency(
            name="pkg",
            group="dependencies",
            constraint="^1.0.0",
            location_key="k",
            resolved_version="1.0.0",
        )
        choice = DependencyVersionChoice(
            dependency=dep,
            available_versions=(RegistryVersion("2.0.0"),),
            latest_stable="2.0.0",
        )
        cycle = build_version_cycle(choice)
        target, index = selection_from_cycle_index(choice, len(cycle))
        assert target == cycle[0]
        assert index == 0
