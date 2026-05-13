"""Launch an external editor on generated changelog release fragments."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from distlift.changelog.builder import (
    apply_edited_release_to_plan,
    validate_edited_release_version_label,
)
from distlift.changelog.formatter import render_release_entry
from distlift.changelog.models import ChangelogUpdatePlan
from distlift.changelog.parser import parse_release_entry_markdown
from distlift.errors import ChangelogError
from distlift.logging_utils import get_logger

log = get_logger(__name__)


def resolve_editor_command() -> str | None:
    """Return the first non-empty editor preference from the environment.

    Returns:
        A shell-style editor command string, or ``None`` when unset.
    """
    # Prefer Git's convention: GIT_EDITOR, then POSIX VISUAL/EDITOR
    for key in ("GIT_EDITOR", "VISUAL", "EDITOR"):
        raw = os.environ.get(key)

        if raw is None:
            continue

        stripped = str(raw).strip()

        if stripped:
            return stripped

    return None


def edit_text_in_external_editor(initial: str) -> str:
    """Write ``initial`` to a temp file, spawn ``$GIT_EDITOR``, return body.

    Args:
        initial: Markdown seeded before the editor opens.

    Returns:
        File contents after the editor process exits successfully.

    Raises:
        ChangelogError: When no editor is configured, invocation fails, or the
            result cannot be read.
    """
    editor_cmd = resolve_editor_command()

    if editor_cmd is None:
        raise ChangelogError(
            "No editor configured (set GIT_EDITOR, VISUAL, or EDITOR)"
        )

    tmp_path_str: str | None = None

    try:
        # Materialize the fragment on disk so editors always receive a path
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".md", prefix="distlift-chg-"
        )
        os.close(fd)

        path = Path(tmp_path_str)

        path.write_text(initial, encoding="utf-8", newline="\n")

        posix_split = os.name != "nt"
        argv = shlex.split(editor_cmd, posix=posix_split) + [str(path)]

        # Block until the editor exits; rely on its status for success
        completed = subprocess.run(
            argv,
            check=False,
            text=True,
            capture_output=True,
        )

        if completed.returncode != 0:
            err_txt = (completed.stderr or "").strip()

            log.error(
                "External editor exited with code %d: %s",
                completed.returncode,
                err_txt or "(no stderr)",
            )

            raise ChangelogError(
                f"Editor exited with status {completed.returncode}; "
                f"{err_txt or 'see logs'}"
            )

        return path.read_text(encoding="utf-8")

    finally:
        if tmp_path_str is not None:
            Path(tmp_path_str).unlink(missing_ok=True)


def maybe_prompt_edit_changelog_entry(
    update_plan: ChangelogUpdatePlan,
    *,
    changelog_prompt_editor: bool,
    skip_changelog_editor: bool,
    dry_run: bool,
) -> ChangelogUpdatePlan:
    """Optionally open an editor so the user can revise the inserted entry.

    Args:
        update_plan: Planned changelog write for one package.
        changelog_prompt_editor: Effective ``changelog.prompt_editor`` flag.
        skip_changelog_editor: CLI-driven skip overriding interactive editing.
        dry_run: When True, return ``update_plan`` unchanged.
    """
    if dry_run:
        return update_plan

    if not changelog_prompt_editor or skip_changelog_editor:
        return update_plan

    # Automated environments lack a tty; keep generated text without blocking
    if not sys.stdin.isatty():
        log.info(
            "Skipping changelog editor (stdin is not a tty); using "
            "generated entry for %s",
            update_plan.path,
        )

        return update_plan

    # Render, edit, parse, and splice the structured release back into the doc
    initial = render_release_entry(update_plan.inserted_release)

    edited_raw = edit_text_in_external_editor(initial)
    edited_entry = parse_release_entry_markdown(edited_raw)

    validate_edited_release_version_label(
        edited_entry,
        update_plan.inserted_release.version_label,
    )

    return apply_edited_release_to_plan(update_plan, edited_entry)
