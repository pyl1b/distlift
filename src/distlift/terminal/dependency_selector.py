"""Console dependency selector using prompt_toolkit."""

from __future__ import annotations

import sys
from collections.abc import Callable

import attrs
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from distlift.dependencies.upgrade_models import (
    DependencySelection,
    DependencyVersionChoice,
    PackageSource,
)
from distlift.dependencies.version_cycle import (
    build_version_cycle,
    selection_from_cycle_index,
    toggle_stable_or_skip,
)
from distlift.terminal.selector_backend import (
    SelectorBackend,
    SelectorCancelledError,
)

_KEY_HELP = (
    "Keys: Up/Down move | Space cycle | Left/Right stable/skip | "
    "Enter approve | Esc cancel"
)

_MIN_COLUMN_WIDTHS = {
    "name": 7,
    "installed": 9,
    "target": 8,
    "group": 5,
    "constraint": 10,
    "lock": 6,
}
_CURSOR_WIDTH = 2
_MARKER_WIDTH = 3
_COLUMN_GAP = 1


@attrs.define(frozen=True)
class _ColumnLayout:
    """Computed column widths for one selector render pass.

    Attributes:
        name: Width of the package name column.
        installed: Width of the installed-version column.
        target: Width of the selected target column.
        group: Width of the dependency group column.
        constraint: Width of the manifest constraint column.
        lock: Width of the lock-version column.
        compact: When True, use the single-line fallback layout.
    """

    name: int
    installed: int
    target: int
    group: int
    constraint: int
    lock: int
    compact: bool = False

    def total_width(self) -> int:
        """Return the total rendered width for the tabular layout.

        Returns:
            Number of columns occupied by the formatted table.
        """
        if self.compact:
            return 0

        return (
            _CURSOR_WIDTH
            + _MARKER_WIDTH
            + self.name
            + self.installed
            + self.target
            + self.group
            + self.constraint
            + self.lock
            + (6 * _COLUMN_GAP)
        )


def _compute_column_layout(
    choices: list[DependencyVersionChoice],
    width: int,
    *,
    target_for_choice: Callable[[DependencyVersionChoice], str],
) -> _ColumnLayout:
    """Compute column widths from content and available terminal space.

    Args:
        choices: Dependency rows shown in the selector.
        width: Available terminal column count.
        target_for_choice: Callable returning the rendered target label.
    """
    if not choices:
        return _ColumnLayout(
            name=_MIN_COLUMN_WIDTHS["name"],
            installed=_MIN_COLUMN_WIDTHS["installed"],
            target=_MIN_COLUMN_WIDTHS["target"],
            group=_MIN_COLUMN_WIDTHS["group"],
            constraint=_MIN_COLUMN_WIDTHS["constraint"],
            lock=_MIN_COLUMN_WIDTHS["lock"],
        )

    name_w = _MIN_COLUMN_WIDTHS["name"]
    installed_w = _MIN_COLUMN_WIDTHS["installed"]
    target_w = _MIN_COLUMN_WIDTHS["target"]
    group_w = _MIN_COLUMN_WIDTHS["group"]
    constraint_w = _MIN_COLUMN_WIDTHS["constraint"]
    lock_w = _MIN_COLUMN_WIDTHS["lock"]

    for choice in choices:
        dep = choice.dependency
        installed_text = _installed_text(dep.installed_version)
        lock_text = _lock_text(dep.resolved_version)
        target_text = _target_text(target_for_choice(choice))
        name_w = max(name_w, len(dep.name))
        installed_w = max(installed_w, len(installed_text))
        target_w = max(target_w, len(target_text))
        group_w = max(group_w, len(dep.group))
        constraint_w = max(constraint_w, len(dep.constraint))
        lock_w = max(lock_w, len(lock_text))

    base = _ColumnLayout(
        name=name_w,
        installed=installed_w,
        target=target_w,
        group=group_w,
        constraint=constraint_w,
        lock=lock_w,
    )

    if base.total_width() > width:
        return _ColumnLayout(
            name=name_w,
            installed=installed_w,
            target=target_w,
            group=group_w,
            constraint=constraint_w,
            lock=lock_w,
            compact=True,
        )

    extra = width - base.total_width()
    name_extra = extra // 3
    constraint_extra = extra // 3
    group_extra = extra - name_extra - constraint_extra

    return _ColumnLayout(
        name=name_w + name_extra,
        installed=installed_w,
        target=target_w,
        group=group_w + group_extra,
        constraint=constraint_w + constraint_extra,
        lock=lock_w,
    )


def _installed_text(installed_version: str | None) -> str:
    """Format the installed column value for one dependency.

    Args:
        installed_version: Version installed in the active environment.
    """
    return installed_version or "?"


def _lock_text(resolved_version: str | None) -> str:
    """Format the lock column value for one dependency.

    Args:
        resolved_version: Resolved lock-file version when known.
    """
    return resolved_version or "?"


def _target_text(label: str) -> str:
    """Format the target column value for one dependency.

    Args:
        label: Selected target label for the dependency row.
    """
    if label.startswith("->"):
        return label

    return f"-> {label}"


def _format_table_row(
    *,
    cursor: str,
    marker: str,
    name: str,
    installed: str,
    target: str,
    group: str,
    constraint: str,
    lock: str,
    layout: _ColumnLayout,
) -> str:
    """Format one fixed-width selector row.

    Args:
        cursor: Cursor prefix for the active row.
        marker: Upgrade marker for the row.
        name: Dependency package name.
        installed: Installed environment version text.
        target: Selected target label.
        group: Manifest dependency group.
        constraint: Manifest constraint string.
        lock: Lock-file version text.
        layout: Column widths for the current render pass.
    """
    return (
        f"{cursor:<{_CURSOR_WIDTH}}"
        f"{_COLUMN_GAP * ' '}"
        f"{marker:<{_MARKER_WIDTH}}"
        f"{_COLUMN_GAP * ' '}"
        f"{name:<{layout.name}}"
        f"{_COLUMN_GAP * ' '}"
        f"{installed:<{layout.installed}}"
        f"{_COLUMN_GAP * ' '}"
        f"{target:<{layout.target}}"
        f"{_COLUMN_GAP * ' '}"
        f"{group:<{layout.group}}"
        f"{_COLUMN_GAP * ' '}"
        f"{constraint:<{layout.constraint}}"
        f"{_COLUMN_GAP * ' '}"
        f"{lock:<{layout.lock}}"
    )


def _format_table_header(layout: _ColumnLayout) -> str:
    """Format the column title row for the selector table.

    Args:
        layout: Column widths for the current render pass.
    """
    return _format_table_row(
        cursor="",
        marker="Upg",
        name="Package",
        installed="Installed",
        target="Target",
        group="Group",
        constraint="Constraint",
        lock="Lock",
        layout=layout,
    )


class PromptToolkitSelectorBackend(SelectorBackend):
    """Interactive selector backed by prompt_toolkit.

    Attributes:
        (none; state is kept per ``select`` invocation.)
    """

    def select(
        self,
        source: PackageSource,
        choices: list[DependencyVersionChoice],
    ) -> list[DependencySelection]:
        """Run the interactive selector for one package source.

        Args:
            source: Package source being reviewed.
            choices: Dependency rows with registry metadata.
        """
        if not choices:
            return []

        return _run_selector_application(source, choices)


def _run_selector_application(
    source: PackageSource,
    choices: list[DependencyVersionChoice],
) -> list[DependencySelection]:
    """Launch the prompt_toolkit application for one source.

    Args:
        source: Package source being reviewed.
        choices: Dependency rows with registry metadata.
    """
    state = _SelectorState(source=source, choices=choices)
    control = FormattedTextControl(lambda: state.render_text())
    list_window = Window(content=control, always_hide_cursor=True)
    root = Layout(HSplit([list_window]))

    bindings = KeyBindings()

    @bindings.add("up")
    def _move_up(event) -> None:
        """Move the active row up."""
        state.move_up()

    @bindings.add("down")
    def _move_down(event) -> None:
        """Move the active row down."""
        state.move_down()

    @bindings.add("home")
    def _move_home(event) -> None:
        """Jump to the first dependency row."""
        state.active_index = 0

    @bindings.add("end")
    def _move_end(event) -> None:
        """Jump to the last dependency row."""
        state.active_index = len(state.choices) - 1

    @bindings.add(" ")
    def _cycle_space(event) -> None:
        """Cycle the active row through available versions."""
        state.cycle_active()

    @bindings.add("left")
    def _toggle_left(event) -> None:
        """Toggle active row between stable and skip."""
        state.toggle_active()

    @bindings.add("right")
    def _toggle_right(event) -> None:
        """Toggle active row between stable and skip."""
        state.toggle_active()

    @bindings.add("enter")
    def _approve(event) -> None:
        """Approve the current source selections."""
        event.app.exit(result=state.build_selections())

    @bindings.add("escape")
    def _cancel(event) -> None:
        """Cancel the selector without approving."""
        event.app.exit(exception=SelectorCancelledError("cancelled"))

    @bindings.add("c-c")
    def _interrupt(event) -> None:
        """Cancel on Ctrl+C."""
        event.app.exit(exception=SelectorCancelledError("cancelled"))

    app = Application(
        layout=root,
        key_bindings=bindings,
        full_screen=False,
    )

    try:
        return app.run()
    except SelectorCancelledError:
        raise
    except KeyboardInterrupt as exc:
        raise SelectorCancelledError("cancelled") from exc


class _SelectorState:
    """Mutable UI state for one selector session.

    Attributes:
        source: Package source being reviewed.
        choices: Dependency rows with registry metadata.
        active_index: Highlighted row index.
        cycle_indices: Per-row cycle index keyed by location_key.
    """

    def __init__(
        self,
        *,
        source: PackageSource,
        choices: list[DependencyVersionChoice],
    ) -> None:
        self.source = source
        self.choices = choices
        self.active_index = 0
        self.cycle_indices: dict[str, int] = {}

        for choice in choices:
            if choice.lookup_error:
                self.cycle_indices[choice.dependency.location_key] = 0
                continue

            _, index = selection_from_cycle_index(choice, 0)
            self.cycle_indices[choice.dependency.location_key] = index

    def move_up(self) -> None:
        """Move the highlight to the previous row."""
        if self.active_index > 0:
            self.active_index -= 1

    def move_down(self) -> None:
        """Move the highlight to the next row."""
        if self.active_index < len(self.choices) - 1:
            self.active_index += 1

    def cycle_active(self) -> None:
        """Advance the active row through the Space cycle."""
        choice = self.choices[self.active_index]
        key = choice.dependency.location_key
        cycle = build_version_cycle(choice)

        if not cycle:
            return

        current = self.cycle_indices.get(key, 0)
        self.cycle_indices[key] = (current + 1) % len(cycle)

    def toggle_active(self) -> None:
        """Toggle the active row between stable and skip."""
        choice = self.choices[self.active_index]
        key = choice.dependency.location_key
        current = self.cycle_indices.get(key, 0)
        _, new_index = toggle_stable_or_skip(choice, current)
        self.cycle_indices[key] = new_index

    def build_selections(self) -> list[DependencySelection]:
        """Materialize the current UI state as selection records.

        Returns:
            Dependency selections for the active source.
        """
        selections: list[DependencySelection] = []

        for choice in self.choices:
            key = choice.dependency.location_key
            index = self.cycle_indices.get(key, 0)
            target, normalized = selection_from_cycle_index(choice, index)
            selections.append(
                DependencySelection(
                    dependency=choice.dependency,
                    target_version=target,
                    cycle_index=normalized,
                )
            )

        return selections

    def render_text(self) -> FormattedText:
        """Render the selector view as formatted terminal text.

        Returns:
            Formatted text lines for prompt_toolkit.
        """
        width = _current_terminal_width()
        layout = _compute_column_layout(
            self.choices,
            width,
            target_for_choice=self._target_label,
        )
        lines: list[tuple[str, str]] = []
        header = (
            f"Source: {self.source.project.name} ({self.source.manager_name})"
        )
        lines.append(("", header + "\n"))
        lines.append(("", ("-" * width) + "\n"))

        if not layout.compact:
            lines.append(("", _format_table_header(layout) + "\n"))

        for index, choice in enumerate(self.choices):
            row = self._format_row(choice, index, width, layout)
            lines.append(("", row + "\n"))

        lines.append(("", ("-" * width) + "\n"))
        lines.append(("", _KEY_HELP + "\n"))
        detail = self._detail_line(width)
        lines.append(("", detail + "\n"))
        return lines

    def _format_row(
        self,
        choice: DependencyVersionChoice,
        index: int,
        width: int,
        layout: _ColumnLayout,
    ) -> str:
        """Format one dependency row for the current terminal width.

        Args:
            choice: Dependency row metadata.
            index: Row index in the current list.
            width: Available terminal column count.
            layout: Column widths for the current render pass.
        """
        prefix = ">" if index == self.active_index else " "
        marker = self._row_marker(choice)
        target = self._target_label(choice)
        dep = choice.dependency
        installed = _installed_text(dep.installed_version)
        lock = _lock_text(dep.resolved_version)

        if layout.compact:
            compact_row = (
                f"{prefix} {marker} {dep.name} inst:{installed} "
                f"-> {target} ({dep.group}) {dep.constraint} lock:{lock}"
            )

            if len(compact_row) <= width:
                return compact_row

            return compact_row[: max(width - 3, 0)] + "..."

        return _format_table_row(
            cursor=prefix,
            marker=marker,
            name=dep.name,
            installed=installed,
            target=_target_text(target),
            group=dep.group,
            constraint=dep.constraint,
            lock=lock,
            layout=layout,
        )

    def _detail_line(self, width: int) -> str:
        """Return a detail line for the active dependency row.

        Args:
            width: Available terminal column count.

        Returns:
            Full detail text for the highlighted row.
        """
        choice = self.choices[self.active_index]
        dep = choice.dependency
        target = self._target_label(choice)
        installed = _installed_text(dep.installed_version)
        lock = _lock_text(dep.resolved_version)
        detail = (
            f"Active: {dep.name} | installed={installed} | target={target} | "
            f"{dep.group} | {dep.constraint} | lock={lock}"
        )

        if len(detail) <= width:
            return detail

        return detail[: max(width - 3, 0)] + "..."

    def _row_marker(self, choice: DependencyVersionChoice) -> str:
        """Return the row status marker for one dependency.

        Args:
            choice: Dependency row metadata.
        """
        if choice.lookup_error:
            return "[!]"

        key = choice.dependency.location_key
        index = self.cycle_indices.get(key, 0)
        target, _ = selection_from_cycle_index(choice, index)

        if target is None:
            return "[ ]"

        return "[x]"

    def _target_label(self, choice: DependencyVersionChoice) -> str:
        """Return the display label for the selected target version.

        Args:
            choice: Dependency row metadata.
        """
        if choice.lookup_error:
            return "(unavailable)"

        key = choice.dependency.location_key
        index = self.cycle_indices.get(key, 0)
        target, _ = selection_from_cycle_index(choice, index)

        if target is None:
            return "(skip)"

        return target


def _current_terminal_width() -> int:
    """Return the live terminal width for selector rendering.

    Returns:
        Current column count from the active prompt_toolkit app when
        available, otherwise a shutil-based fallback.
    """
    try:
        from prompt_toolkit.application import get_app

        app = get_app()
        columns = app.output.get_size().columns
        return max(40, columns)
    except Exception:
        return shutil_get_terminal_width()


def shutil_get_terminal_width() -> int:
    """Return terminal width with a safe fallback.

    Returns:
        Terminal column count, at least 80 when detection fails.
    """
    try:
        from shutil import get_terminal_size

        return max(80, get_terminal_size((80, 24)).columns)
    except Exception:
        return 80


def terminal_is_interactive() -> bool:
    """Return True when stdin and stdout are both TTYs.

    Returns:
        Whether interactive terminal UI may run safely.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()
