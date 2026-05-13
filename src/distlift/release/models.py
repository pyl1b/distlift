from __future__ import annotations

from pathlib import Path

import attrs

from distlift.changelog.models import ChangelogUpdatePlan
from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
    VersionSource,
)
from distlift.versioning.models import ResolvedVersion


@attrs.define
class ReleaseTarget:
    """Describes one package root and manifest for a release run.

    Attributes:
        language: Project language used to pick the manifest adapter.
        root: Absolute or repo-relative root directory for this package.
        manifest_path: Path to the version manifest file to read or update.
        version_source: Whether the canonical version lives in the manifest
            or only in Git tags.
        package_name: Optional monorepo package name used in tags and logs.
    """

    language: Language
    root: Path
    manifest_path: Path
    version_source: VersionSource = VersionSource.MANIFEST
    package_name: str | None = None


@attrs.define
class SimpleReleaseRequest:
    """Inputs for planning a single-package (simple mode) release.

    Attributes:
        repo_root: Repository root passed to Git and discovery.
        config: Fully merged resolved configuration for the run.
        bump: Semantic bump to apply when no explicit_version is set.
        explicit_version: When set, this exact version string is used.
        dry_run: When True, planners mark the plan as non-executing.
        skip_changelog: When True, changelog mutations are not planned.
        skip_changelog_editor: When True, do not open an editor on generated
            changelog entries before writing (CLI override).
    """

    repo_root: Path
    config: ResolvedConfig
    bump: BumpKind | None = None
    explicit_version: str | None = None
    dry_run: bool = False
    skip_changelog: bool = False
    skip_changelog_editor: bool = False


@attrs.define
class MonorepoReleaseRequest:
    """Inputs for planning a monorepo release over managed packages.

    Attributes:
        repo_root: Repository root passed to Git and discovery.
        config: Fully merged resolved configuration including monorepo
            package declarations.
        default_bump: Bump applied to each selected package when not pinned.
        selected_packages: Optional subset of package names to consider.
        all_changed: When True, include only packages with commits since their
            last tag; when False, use selection or all declared packages.
        dry_run: When True, planners mark the plan as non-executing.
        skip_changelog: When True, changelog mutations are not planned.
        skip_changelog_editor: When True, do not open an editor on generated
            changelog entries before writing (CLI override).
    """

    repo_root: Path
    config: ResolvedConfig
    default_bump: BumpKind = BumpKind.PATCH
    selected_packages: list[str] = attrs.Factory(list)
    all_changed: bool = True
    dry_run: bool = False
    skip_changelog: bool = False
    skip_changelog_editor: bool = False


@attrs.define
class PackageReleasePlan:
    """Per-package slice of a release plan (version and manifest policy).

    Attributes:
        target: Language, paths, and naming for this package.
        resolved_version: Current and next versions plus computed tag name.
        update_manifest: When False, manifests are left unchanged (e.g.
            dynamic or tag-only versioning).
        changelog_update: Optional changelog mutation applied before manifests.
    """

    target: ReleaseTarget
    resolved_version: ResolvedVersion
    update_manifest: bool
    changelog_update: ChangelogUpdatePlan | None = None


@attrs.define
class ReleasePlan:
    """A fully computed, side-effect-free description of one release run.

    Attributes:
        mode: Whether this is a simple or monorepo release.
        packages: One entry per package being released in this run.
        commit_message: The Git commit message to use.
        tag_names: All tag names to create (one per package).
        remotes: Remote names to push the commit and tags to.
        dry_run: When True the executor logs actions but does not write.
        repo_root: Absolute path to the root of the repository.
        changelog_prompt_editor: Snapshot of ``changelog.prompt_editor`` when
            the plan was built (whether interactive editing is desired).
        skip_changelog_editor: When True, skip opening an editor regardless of
            ``changelog_prompt_editor``.

    Properties:
        has_manifest_updates: True when any package requires a manifest
            version write before tagging.
        has_changelog_updates: True when any package carries a changelog plan.
    """

    mode: ReleaseMode
    packages: list[PackageReleasePlan]
    commit_message: str
    tag_names: list[str]
    remotes: list[str]
    dry_run: bool
    repo_root: Path
    changelog_prompt_editor: bool = True
    skip_changelog_editor: bool = False

    @property
    def has_manifest_updates(self) -> bool:
        return any(p.update_manifest for p in self.packages)

    @property
    def has_changelog_updates(self) -> bool:
        return any(p.changelog_update is not None for p in self.packages)


@attrs.define
class ReleaseResult:
    """Outcome of executing or simulating a release plan.

    Attributes:
        success: True when the run completed without fatal errors.
        dry_run: Mirrors the plan flag; True when no Git writes occurred.
        tag_names: Tags that were created or would have been created.
        commit_sha: Hash of the release commit when one was made.
        pushed_remotes: Remotes that received branch and tag pushes.
        error: Human-readable failure message when success is False.
    """

    success: bool
    dry_run: bool
    tag_names: list[str] = attrs.Factory(list)
    commit_sha: str | None = None
    pushed_remotes: list[str] = attrs.Factory(list)
    error: str | None = None
