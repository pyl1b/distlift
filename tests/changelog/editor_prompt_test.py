"""Tests for optional external-editor changelog flows."""

from pathlib import Path

from distlift.changelog.editor_prompt import maybe_prompt_edit_changelog_entry
from distlift.changelog.formatter import render_release_entry
from distlift.changelog.models import (
    ChangelogDocument,
    ChangelogReleaseEntry,
    ChangelogSection,
    ChangelogUpdatePlan,
)


def _minimal_plan(tmp_path: Path) -> ChangelogUpdatePlan:
    """Return a tiny ``ChangelogUpdatePlan`` for editor gating tests.

    Args:
        tmp_path: Pytest temporary directory for the changelog path.
    """
    inserted = ChangelogReleaseEntry(
        version_label="1.0.0",
        date_iso="2024-01-01",
        sections=[
            ChangelogSection(title="Added", bullets=["seed"]),
        ],
        link_ref="1.0.0",
    )
    doc = ChangelogDocument(
        title_line="# C",
        intro_lines=[],
        releases=[inserted],
        footer_links={},
    )

    return ChangelogUpdatePlan(
        path=tmp_path / "CHANGELOG.md",
        inserted_release=inserted,
        new_document=doc,
        unreleased_placeholder=inserted,
    )


class TestMaybePromptEditChangelogEntry:
    """Cover stdin, flags, and monkey-patched editor behavior."""

    def test_skips_when_dry_run(self, tmp_path: Path) -> None:
        """Dry-run planning never opens an editor."""
        plan = _minimal_plan(tmp_path)

        out = maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=True,
            skip_changelog_editor=False,
            dry_run=True,
        )

        assert out is plan

    def test_skips_when_prompt_disabled(self, tmp_path: Path) -> None:
        """Config may disable interactive editing entirely."""
        plan = _minimal_plan(tmp_path)

        out = maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=False,
            skip_changelog_editor=False,
            dry_run=False,
        )

        assert out is plan

    def test_skips_when_cli_override(self, tmp_path: Path) -> None:
        """CLI ``--no-changelog-editor`` bypasses the editor."""
        plan = _minimal_plan(tmp_path)

        out = maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=True,
            skip_changelog_editor=True,
            dry_run=False,
        )

        assert out is plan

    def test_skips_when_stdin_not_tty(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Non-interactive runs keep generated Markdown."""
        plan = _minimal_plan(tmp_path)
        monkeypatch.setattr(
            "distlift.changelog.editor_prompt.sys.stdin.isatty",
            lambda: False,
        )

        out = maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=True,
            skip_changelog_editor=False,
            dry_run=False,
        )

        assert out is plan

    def test_invokes_editor_when_tty(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """TTY hosts parse edited Markdown back into the document model."""
        plan = _minimal_plan(tmp_path)
        monkeypatch.setattr(
            "distlift.changelog.editor_prompt.sys.stdin.isatty",
            lambda: True,
        )

        def fake_edit(
            initial: str,
            *,
            editor_command: str | None = None,
        ) -> str:
            entry = plan.inserted_release
            updated = ChangelogReleaseEntry(
                version_label=entry.version_label,
                date_iso=entry.date_iso,
                sections=[
                    ChangelogSection(
                        title="Added",
                        bullets=["from-editor"],
                    ),
                ],
                link_ref=entry.link_ref,
            )

            return render_release_entry(updated)

        monkeypatch.setattr(
            "distlift.changelog.editor_prompt.edit_text_in_external_editor",
            fake_edit,
        )

        out = maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=True,
            skip_changelog_editor=False,
            dry_run=False,
        )

        assert out.inserted_release.sections[0].bullets == ["from-editor"]

    def test_forwards_editor_command(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """The ``editor_command`` kwarg is threaded into the editor helper."""
        plan = _minimal_plan(tmp_path)
        monkeypatch.setattr(
            "distlift.changelog.editor_prompt.sys.stdin.isatty",
            lambda: True,
        )

        captured: dict[str, str | None] = {"editor_command": "<missing>"}

        def fake_edit(
            initial: str,
            *,
            editor_command: str | None = None,
        ) -> str:
            captured["editor_command"] = editor_command
            return render_release_entry(plan.inserted_release)

        monkeypatch.setattr(
            "distlift.changelog.editor_prompt.edit_text_in_external_editor",
            fake_edit,
        )

        maybe_prompt_edit_changelog_entry(
            plan,
            changelog_prompt_editor=True,
            skip_changelog_editor=False,
            dry_run=False,
            editor_command="code --wait",
        )

        assert captured["editor_command"] == "code --wait"
