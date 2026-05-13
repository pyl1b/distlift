"""Structured inputs and outcomes for ``distlift deploy``."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.models import Language, ResolvedConfig


@attrs.define
class DeployRequest:
    """Inputs for a deploy tag run.

    Attributes:
        repo_root: Repository root directory path.
        config: Merged effective configuration.
        dry_run: When True, skip creating or pushing the deploy tag.
        tag_prefix: Optional override for the tag prefix (``{prefix}_{N}``);
            when None, ``config.deploy.tag_prefix`` is used.
        verify_indexes: Optional override for registry verification; when
            None, ``config.deploy.verify_indexes`` is used.
    """

    repo_root: Path
    config: ResolvedConfig
    dry_run: bool = False
    tag_prefix: str | None = None
    verify_indexes: bool | None = None


@attrs.define
class DeployPackageCheck:
    """Result of verifying one package against a package index.

    Attributes:
        label: Display label (monorepo package name or repo folder name).
        language: Project language used for the check.
        registry_name: Name as published (PyPI / npm package name).
        version: Version string that was required on the index.
        ok: True when the version was found.
        detail: Error or diagnostic text when ``ok`` is False.
    """

    label: str
    language: Language
    registry_name: str
    version: str
    ok: bool
    detail: str | None = None


@attrs.define
class DeployResult:
    """Outcome of ``run_deploy``.

    Attributes:
        success: True when the deploy tag was created (or dry-run planned)
            without failure.
        dry_run: Mirrors the request dry-run flag.
        tag_name: Full deploy tag name (e.g. ``deploy_2``).
        pushed_remotes: Remotes that received the tag push.
        checks: Per-package index verification rows when verification ran.
        error: Human-readable failure reason when ``success`` is False.
    """

    success: bool
    dry_run: bool
    tag_name: str = ""
    pushed_remotes: list[str] = attrs.Factory(list)
    checks: list[DeployPackageCheck] = attrs.Factory(list)
    error: str | None = None
