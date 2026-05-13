from __future__ import annotations

from distlift.config.models import ReleaseMode, ResolvedConfig, VersionSource
from distlift.release.models import (
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
)
from distlift.versioning.formatter import format_version
from distlift.versioning.models import ResolvedVersion


def build_commit_message(plans: list[PackageReleasePlan]) -> str:
    if len(plans) == 1:
        ver = format_version(plans[0].resolved_version.next)
        name = plans[0].target.package_name
        if name:
            return f"chore: release {name} {ver}"
        return f"chore: release {ver}"
    parts = ", ".join(
        f"{p.target.package_name or 'package'} {format_version(p.resolved_version.next)}"
        for p in plans
    )
    return f"chore: release {parts}"


def build_tag_messages(plans: list[PackageReleasePlan]) -> dict[str, str]:
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
    repo_root: "Path",  # noqa: F821
    dry_run: bool = False,
) -> ReleasePlan:
    from pathlib import Path

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
    return target.version_source == VersionSource.TAG
