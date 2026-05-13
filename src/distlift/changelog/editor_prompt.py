"""Launch an external editor on generated changelog release fragments."""

from __future__ import annotations

import os
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
from distlift.editor import launch_editor_blocking, resolve_editor_command
from distlift.errors import ChangelogError, ConfigurationError
from distlift.logging_utils import get_logger

log = get_logger(__name__)

# Re-exported for backward compatibility with callers and tests that
# patched ``distlift.changelog.editor_prompt.resolve_editor_command``.
__all__ = [
    "resolve_editor_command",
    "edit_text_in_external_editor",
    "maybe_prompt_edit_changelog_entry",
]


_CHANGELOG_SKIP_HINT = (
    "To skip this prompt instead, pass --no-changelog-editor "
    "or set changelog.prompt_editor = false in your config."
)


def edit_text_in_external_editor(
    initial: str,
    *,
    editor_command: str | None = None,
) -> str:
    """Write ``initial`` to a temp file, spawn the editor, return body.

    Args:
        initial: Markdown seeded before the editor opens.
        editor_command: Optional editor command sourced from distlift's
            configuration; used when no editor env var is set.

    Returns:
        File contents after the editor process exits successfully.

    Raises:
        ChangelogError: When no editor is configured, invocation fails, or the
            result cannot be read.
    """
    tmp_path_str: str | None = None

    try:
        # Materialize the fragment on disk so editors always receive a path
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".md", prefix="distlift-chg-"
        )
        os.close(fd)

        path = Path(tmp_path_str)

        path.write_text(initial, encoding="utf-8", newline="\n")

        # Block until the editor exits; rely on its status for success
        try:
            exit_code = launch_editor_blocking(
                path,
                skip_hint=_CHANGELOG_SKIP_HINT,
                config_editor=editor_command,
            )
        except ConfigurationError as exc:
            raise ChangelogError(str(exc)) from exc

        if exit_code != 0:
            log.error(
                "External editor exited with code %d while editing %s",
                exit_code,
                path,
            )

            raise ChangelogError(
                f"Editor exited with status {exit_code}; see logs"
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
    editor_command: str | None = None,
) -> ChangelogUpdatePlan:
    """Optionally open an editor so the user can revise the inserted entry.

    Args:
        update_plan: Planned changelog write for one package.
        changelog_prompt_editor: Effective ``changelog.prompt_editor`` flag.
        skip_changelog_editor: CLI-driven skip overriding interactive editing.
        dry_run: When True, return ``update_plan`` unchanged.
        editor_command: Optional editor command sourced from distlift's
            configuration; used when no editor env var is set.
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

    edited_raw = edit_text_in_external_editor(
        initial, editor_command=editor_command
    )
    edited_entry = parse_release_entry_markdown(edited_raw)

    validate_edited_release_version_label(
        edited_entry,
        update_plan.inserted_release.version_label,
    )

    return apply_edited_release_to_plan(update_plan, edited_entry)
