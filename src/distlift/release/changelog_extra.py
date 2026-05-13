"""Attach changelog mutations onto finalized ``ReleasePlan`` instances."""

from __future__ import annotations

from datetime import date

import attrs

from distlift.changelog.builder import build_changelog_update_plan
from distlift.config.models import (
    ManagedPackageConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.release.models import PackageReleasePlan, ReleasePlan
from distlift.vcs.git import GitRepository
from distlift.versioning.formatter import format_version
from distlift.versioning.resolver import find_latest_matching_tag


def finalize_plan_with_changelog(
    plan: ReleasePlan,
    *,
    git_repo: GitRepository,
    tags: list[str],
    config: ResolvedConfig,
    skip_changelog: bool,
) -> ReleasePlan:
    """Attach changelog mutations for each package when enabled.

    Args:
        plan: Baseline release plan built without changelog mutations.
        git_repo: Git accessor rooted at ``plan.repo_root``.
        tags: All tag names available when locating prior releases.
        config: Effective repository configuration including changelog policy.
        skip_changelog: When True, skip changelog planning regardless of
            config.
    """
    if skip_changelog or not config.changelog.enabled:
        return plan

    enriched: list[PackageReleasePlan] = []

    if plan.mode == ReleaseMode.SIMPLE:
        for pkg_plan in plan.packages:
            last_tag = find_latest_matching_tag(
                tags,
                config.tag_template,
                config.version_format,
                pkg_plan.target.package_name,
            )

            changelog_path = (plan.repo_root / config.changelog.path).resolve()

            update_plan = build_changelog_update_plan(
                git_repo,
                changelog_path,
                None,
                last_tag,
                format_version(pkg_plan.resolved_version.next),
                pkg_plan.resolved_version.tag_name,
                date.today(),
                config.changelog,
            )

            enriched.append(
                attrs.evolve(pkg_plan, changelog_update=update_plan)
            )

        return attrs.evolve(plan, packages=enriched)

    packages_by_name: dict[str, ManagedPackageConfig] = {
        pkg.name: pkg for pkg in config.monorepo.packages
    }

    for pkg_plan in plan.packages:
        name = pkg_plan.target.package_name

        if name is None:
            enriched.append(pkg_plan)

            continue

        pkg_cfg = packages_by_name[name]
        template = pkg_cfg.tag_template or f"v{{version}}-{pkg_cfg.name}"

        last_tag = find_latest_matching_tag(
            tags,
            template,
            pkg_cfg.version_format,
            pkg_cfg.name,
        )

        rel_changelog = pkg_cfg.changelog_path or config.changelog.path

        changelog_path = (
            plan.repo_root / pkg_cfg.path / rel_changelog
        ).resolve()

        update_plan = build_changelog_update_plan(
            git_repo,
            changelog_path,
            pkg_cfg.path,
            last_tag,
            format_version(pkg_plan.resolved_version.next),
            pkg_plan.resolved_version.tag_name,
            date.today(),
            config.changelog,
        )

        enriched.append(attrs.evolve(pkg_plan, changelog_update=update_plan))

    return attrs.evolve(plan, packages=enriched)
