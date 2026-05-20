"""Run configured lifecycle hooks as subprocesses."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from distlift.config.models import HooksConfig, HookSpec, ResolvedConfig
from distlift.errors import HookExecutionError
from distlift.logging_utils import get_logger

log = get_logger(__name__)


def build_hook_env(
    *,
    event: str,
    repo_root: Path,
    dry_run: bool,
    tag_names: Sequence[str] | None = None,
    pushed_remotes: Sequence[str] | None = None,
    commit_sha: str | None = None,
    package: str | None = None,
    error: str | None = None,
    dependency_update_count: int | None = None,
    dependency_update_projects: Sequence[str] | None = None,
    dependency_update_files: Sequence[str] | None = None,
    dependency_update_dependencies: Sequence[str] | None = None,
    dependency_update_triggers: Sequence[str] | None = None,
) -> dict[str, str]:
    """Assemble environment variables passed to every hook subprocess.

    Args:
        event: Hook event name (``tag_pushed``, ``build_failed``, etc.).
        repo_root: Repository root directory for this run.
        dry_run: When True, hooks should observe ``DISTLIFT_DRY_RUN=1``.
        tag_names: Optional tag names for this release attempt.
        pushed_remotes: Remotes fully pushed before success or failure.
        commit_sha: Optional release commit hash when known.
        package: Optional monorepo package label for per-package events.
        error: Optional error text for failure events.
        dependency_update_count: Number of dependency declarations updated.
        dependency_update_projects: Dependent project names (sorted).
        dependency_update_files: Manifest paths that were updated (sorted).
        dependency_update_dependencies: Dependency names that changed (sorted).
        dependency_update_triggers: Released packages that triggered updates.
    """
    env: dict[str, str] = {
        "DISTLIFT_EVENT": event,
        "DISTLIFT_REPO_ROOT": str(repo_root.resolve()),
        "DISTLIFT_DRY_RUN": "1" if dry_run else "0",
    }

    if tag_names is not None:
        env["DISTLIFT_TAG_NAMES"] = ",".join(tag_names)

    if pushed_remotes is not None:
        env["DISTLIFT_PUSHED_REMOTES"] = ",".join(pushed_remotes)

    if commit_sha is not None:
        env["DISTLIFT_COMMIT_SHA"] = commit_sha

    if package is not None:
        env["DISTLIFT_PACKAGE"] = package

    if error is not None:
        env["DISTLIFT_ERROR"] = error

    if dependency_update_count is not None:
        env["DISTLIFT_DEPENDENCY_UPDATE_COUNT"] = str(dependency_update_count)

    if dependency_update_projects is not None:
        env["DISTLIFT_DEPENDENCY_UPDATE_PROJECTS"] = ",".join(
            sorted(dependency_update_projects)
        )

    if dependency_update_files is not None:
        env["DISTLIFT_DEPENDENCY_UPDATE_FILES"] = ",".join(
            sorted(str(p) for p in dependency_update_files)
        )

    if dependency_update_dependencies is not None:
        env["DISTLIFT_DEPENDENCY_UPDATE_DEPENDENCIES"] = ",".join(
            sorted(dependency_update_dependencies)
        )

    if dependency_update_triggers is not None:
        env["DISTLIFT_DEPENDENCY_UPDATE_TRIGGERS"] = ",".join(
            sorted(dependency_update_triggers)
        )

    return env


def run_config_hooks(
    config: ResolvedConfig,
    event: str,
    repo_root: Path,
    *,
    dry_run: bool,
    tag_names: Sequence[str] | None = None,
    pushed_remotes: Sequence[str] | None = None,
    commit_sha: str | None = None,
    package: str | None = None,
    error: str | None = None,
) -> None:
    """Run hooks for ``event`` using merged config (no :class:`ReleasePlan`).

    Args:
        config: Resolved configuration with hook command lists.
        event: Hook event name (attribute on ``HooksConfig``).
        repo_root: Repository root used as hook working directory.
        dry_run: When True, skip hook execution.
        tag_names: Optional tag name sequence for release-related hooks.
        pushed_remotes: Optional remotes list for push-related hooks.
        commit_sha: Optional commit hash when known.
        package: Optional package label for monorepo build or publish hooks.
        error: Optional error text for failure events.
    """
    if dry_run:
        return

    specs = specs_for_event(config.hooks, event)

    if not specs:
        return

    extra = build_hook_env(
        event=event,
        repo_root=repo_root,
        dry_run=dry_run,
        tag_names=tag_names,
        pushed_remotes=pushed_remotes,
        commit_sha=commit_sha,
        package=package,
        error=error,
    )
    run_hook_specs(
        specs,
        repo_root=repo_root,
        extra_env=extra,
    )


def run_hook_specs(
    specs: list[HookSpec],
    *,
    repo_root: Path,
    extra_env: Mapping[str, str],
) -> None:
    """Execute hook commands in order; abort on the first non-zero exit.

    Args:
        specs: Hook entries resolved for one event.
        repo_root: Working directory for subprocesses.
        extra_env: Variables merged into ``os.environ`` for each hook
            (caller-supplied names should include ``DISTLIFT_*`` keys).
    """
    if not specs:
        return

    root = repo_root.resolve()
    child_env: dict[str, str] = dict(os.environ)
    child_env.update({k: str(v) for k, v in extra_env.items()})

    for spec in specs:
        _run_one_spec(spec, cwd=root, child_env=child_env)


def _run_one_spec(
    spec: HookSpec,
    *,
    cwd: Path,
    child_env: dict[str, str],
) -> None:
    """Launch a single hook subprocess and enforce a successful exit.

    Args:
        spec: Either a shell string or an argument vector.
        cwd: Working directory for the child process.
        child_env: Environment mapping including parent ``os.environ`` plus
            ``DISTLIFT_*`` variables for this event.
    """
    if spec.argv is not None:
        log.info("Running hook argv: %s", spec.argv)
        proc = subprocess.run(
            spec.argv,
            cwd=cwd,
            env=child_env,
            shell=False,
            capture_output=True,
            text=True,
        )
        cmd_repr = " ".join(spec.argv)
    else:
        assert spec.shell is not None
        log.info("Running hook shell: %s", spec.shell)
        proc = subprocess.run(
            spec.shell,
            cwd=cwd,
            env=child_env,
            shell=True,
            capture_output=True,
            text=True,
        )
        cmd_repr = spec.shell

    if proc.returncode == 0:
        return

    log.error(
        "Hook failed (exit %d) for %s; stdout: %s; stderr: %s",
        proc.returncode,
        cmd_repr,
        proc.stdout or "",
        proc.stderr or "",
    )
    raise HookExecutionError(
        f"Hook command failed with exit code {proc.returncode}: {cmd_repr}"
    )


def specs_for_event(config: HooksConfig, event: str) -> list[HookSpec]:
    """Return the hook list for a named event.

    Args:
        config: Effective merged hooks configuration.
        event: Event field name on ``HooksConfig`` (e.g. ``tag_pushed``).
    """
    if not hasattr(config, event):
        msg = f"Unknown hook event name: {event}"
        raise ValueError(msg)
    return list(getattr(config, event))
