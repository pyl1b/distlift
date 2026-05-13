"""Resolve and launch the user's preferred external text editor.

This module centralizes editor handling so both the changelog editing flow
and the configuration ``edit-user`` / ``edit-system`` commands share the
same convention for picking an editor.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from distlift.errors import ConfigurationError
from distlift.logging_utils import get_logger

log = get_logger(__name__)

EDITOR_ENV_VARS: tuple[str, ...] = ("GIT_EDITOR", "VISUAL", "EDITOR")
"""Priority-ordered environment variable names consulted to find an editor.

``GIT_EDITOR`` is Git's own override and wins over the older POSIX names.
``VISUAL`` is the POSIX convention for a full-screen editor (vim, nano,
``code --wait``...). ``EDITOR`` is the POSIX fallback for a basic editor.
"""


def resolve_editor_command(
    config_editor: str | None = None,
) -> str | None:
    """Return the first non-empty editor preference for this run.

    Resolution order:

    1. ``GIT_EDITOR`` environment variable
    2. ``VISUAL`` environment variable
    3. ``EDITOR`` environment variable
    4. ``config_editor`` (e.g. merged ``ResolvedConfig.editor`` from TOML or
       ``DISTLIFT_EDITOR``) when all env vars above are unset or blank

    Args:
        config_editor: Optional editor command sourced from distlift's
            configuration layer, used as a last-resort fallback.

    Returns:
        A shell-style editor command string, or ``None`` when unset.
    """
    # Prefer Git's convention: GIT_EDITOR, then POSIX VISUAL/EDITOR
    for key in EDITOR_ENV_VARS:
        raw = os.environ.get(key)

        if raw is None:
            continue

        stripped = str(raw).strip()

        if stripped:
            return stripped

    # Final fallback: distlift's own ``editor`` config value
    if config_editor is not None:
        stripped_cfg = str(config_editor).strip()

        if stripped_cfg:
            return stripped_cfg

    return None


def format_missing_editor_message(skip_hint: str | None = None) -> str:
    """Return a verbose error string explaining how to configure an editor.

    Args:
        skip_hint: Optional trailing sentence describing how the caller can
            skip the editor prompt entirely (CLI flag or config key).
    """
    base = (
        "No editor configured. Set one of these environment "
        "variables to a command that opens a file for editing "
        "(checked in this priority order): "
        "GIT_EDITOR (Git-specific override, same variable Git "
        "itself consults for commit messages), "
        "VISUAL (POSIX convention for a full-screen editor, "
        "e.g. 'vim', 'nano', or 'code --wait'), or "
        "EDITOR (POSIX fallback for a basic editor command, "
        "e.g. 'notepad' on Windows). "
        "As a tool-specific fallback you can also set "
        "'editor' in your distlift config "
        "(distlift.toml / user / system) or "
        "DISTLIFT_EDITOR in the environment."
    )

    if skip_hint:
        return f"{base} {skip_hint}"

    return base


def _split_editor_command(editor_cmd: str) -> list[str]:
    """Split a configured editor command into an argv list.

    Args:
        editor_cmd: Raw editor command as found in the environment.
    """
    # POSIX-style splitting on Unix, Windows-style splitting on win32
    posix_split = os.name != "nt"

    return shlex.split(editor_cmd, posix=posix_split)


def launch_editor_blocking(
    path: Path,
    *,
    skip_hint: str | None = None,
    config_editor: str | None = None,
) -> int:
    """Open ``path`` in the user's editor and wait for the process to exit.

    Args:
        path: Filesystem path to open in the editor. The caller is
            responsible for ensuring the path exists.
        skip_hint: Optional hint included in the error raised when no editor
            is configured (e.g. CLI flag or config key to skip the prompt).
        config_editor: Optional editor command sourced from distlift's
            configuration layer, used when no editor env var is set.

    Returns:
        The editor subprocess exit code.

    Raises:
        ConfigurationError: When no editor source (env var or config) is set.
    """
    editor_cmd = resolve_editor_command(config_editor)

    if editor_cmd is None:
        raise ConfigurationError(format_missing_editor_message(skip_hint))

    argv = _split_editor_command(editor_cmd) + [str(path)]

    log.debug("Launching editor: %s on %s", argv[0], path)

    # Block until the editor exits; do not capture stdio so the editor can
    # take over the controlling terminal (required for vim, nano, etc.).
    completed = subprocess.run(argv, check=False)

    log.log(
        5,
        "Editor exited with status %d for %s",
        completed.returncode,
        path,
    )

    return completed.returncode
