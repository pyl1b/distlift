from __future__ import annotations

from pathlib import Path

from distlift.config.models import ReleaseMode, ResolvedConfig, VersionSource
from distlift.release.models import (
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
)
from distlift.versioning.formatter import format_version
from distlift.versioning.models import ResolvedVersion


def build_commit_message(plans: list[PackageReleasePlan]) -> str:
    """Return a conventional commit message summarizing the release set.

    Args:
        plans: One or more package plans included in this release.
    """
    if len(plans) == 1:
        ver = format_version(plans[0].resolved_version.next)
        name = plans[0].target.package_name
        if name:
            return f"chore: release {name} {ver}"
        return f"chore: release {ver}"
    parts = ", ".join(
        f"{p.target.package_name or 'package'} "
        f"{format_version(p.resolved_version.next)}"
        for p in plans
    )
    return f"chore: release {parts}"


def build_tag_messages(plans: list[PackageReleasePlan]) -> dict[str, str]:
    """Map each tag name to a short default annotation message.

    Args:
        plans: Package plans whose resolved_version supplies tag_name.
    """
    return {
        plan.resolved_version.tag_name: (
            f"Release {format_version(plan.resolved_version.next)}"
        )
        for plan in plans
    }


def plan_simple_release(
    target: ReleaseTarget,
    resolved_version: ResolvedVersion,
    config: ResolvedConfig,
    dry_run: bool = False,
) -> ReleasePlan:
    """Assemble a simple-mode release plan for a single target.

    Args:
        target: Resolved project paths and language metadata.
        resolved_version: Current and next versions plus tag name.
        config: Resolved global configuration (remotes, templates, etc.).
        dry_run: When True, marks the plan as a simulation-only run.
    """
    update_manifest = not _is_dynamic(target)
    package_plan = PackageReleasePlan(
        target=target,
        resolved_version=resolved_version,
        update_manifest=update_manifest,
    )
    commit_msg = build_commit_message([package_plan])
    return ReleasePlan(
        mode=ReleaseMode.SIMPLE,
        packages=[package_plan],
        commit_message=commit_msg,
        tag_names=[resolved_version.tag_name],
        remotes=config.remotes,
        dry_run=dry_run,
        repo_root=target.root,
    )


def plan_monorepo_release(
    plans: list[PackageReleasePlan],
    config: ResolvedConfig,
    repo_root: Path,
    dry_run: bool = False,
) -> ReleasePlan:
    """Assemble a monorepo release plan spanning multiple packages.

    Args:
        plans: Per-package plans that share one commit in monorepo mode.
        config: Resolved global configuration (remotes, etc.).
        repo_root: Absolute repository root for Git operations.
        dry_run: When True, marks the plan as a simulation-only run.
    """
    commit_msg = build_commit_message(plans)
    tag_names = [p.resolved_version.tag_name for p in plans]
    return ReleasePlan(
        mode=ReleaseMode.MONOREPO,
        packages=plans,
        commit_message=commit_msg,
        tag_names=tag_names,
        remotes=config.remotes,
        dry_run=dry_run,
        repo_root=repo_root,
    )


def _is_dynamic(target: ReleaseTarget) -> bool:
    """Return True when the manifest must not be written for this target.

    Args:
        target: Release target whose version_source is inspected.
    """
    return target.version_source == VersionSource.TAG
