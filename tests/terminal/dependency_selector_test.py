"""Tests for the dependency selector terminal UI."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language
from distlift.dependencies.models import DependencyProject
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencyVersionChoice,
    PackageSource,
    RegistryVersion,
)
from distlift.terminal.dependency_selector import (
    _compute_column_layout,
    _format_table_header,
    _SelectorState,
)


def _sample_state() -> _SelectorState:
    manifest = Path("pyproject.toml")
    source = PackageSource(
        project=DependencyProject(
            name="distlift",
            dependency_name="distlift",
            language=Language.PYTHON,
            root=Path("."),
            manifest_path=manifest,
        ),
        manager_name="pip",
    )
    choices = [
        DependencyVersionChoice(
            dependency=DeclaredDependency(
                name="attrs",
                group="dependencies",
                constraint="attrs>=23.2",
                location_key="a",
            ),
            available_versions=(RegistryVersion("26.1.0"),),
            latest_stable="26.1.0",
        ),
        DependencyVersionChoice(
            dependency=DeclaredDependency(
                name="prompt-toolkit",
                group="dependencies",
                constraint="prompt-toolkit>=3.0",
                location_key="c",
            ),
            available_versions=(RegistryVersion("3.0.52"),),
            latest_stable="3.0.52",
        ),
    ]
    return _SelectorState(source=source, choices=choices)


class TestSelectorRendering:
    """Tests for selector text layout."""

    def test_render_text_puts_each_row_on_its_own_line(self) -> None:
        state = _sample_state()
        rendered = state.render_text()
        text = "".join(fragment for _, fragment in rendered)
        lines = [line for line in text.splitlines() if line.strip()]
        dependency_lines = [
            line
            for line in lines
            if line.lstrip().startswith(("[x]", "[ ]", "[!]", ">"))
            or " attrs" in line
            or " click" in line
        ]
        assert len(dependency_lines) >= 2
        assert "attrs" in dependency_lines[0]
        assert "prompt-toolkit" in dependency_lines[1]

    def test_render_text_includes_column_titles(self) -> None:
        state = _sample_state()
        rendered = state.render_text()
        text = "".join(fragment for _, fragment in rendered)
        assert "Package" in text
        assert "Installed" in text
        assert "Target" in text
        assert "Group" in text
        assert "Constraint" in text
        assert "Lock" in text

    def test_column_header_order_places_installed_before_target(self) -> None:
        state = _sample_state()
        layout = _compute_column_layout(
            state.choices,
            160,
            target_for_choice=state._target_label,
        )
        header = _format_table_header(layout)
        installed_index = header.index("Installed")
        target_index = header.index("Target")
        group_index = header.index("Group")
        assert installed_index < target_index < group_index

    def test_format_row_uses_compact_layout_on_narrow_width(self) -> None:
        state = _sample_state()
        choice = state.choices[0]
        layout = _compute_column_layout(
            state.choices,
            50,
            target_for_choice=state._target_label,
        )
        row = state._format_row(choice, 0, width=50, layout=layout)
        assert "attrs" in row
        assert len(row) <= 50

    def test_column_layout_expands_with_available_width(self) -> None:
        state = _sample_state()
        layout = _compute_column_layout(
            state.choices,
            160,
            target_for_choice=state._target_label,
        )
        assert not layout.compact
        header = _format_table_header(layout)
        assert len(header) > 80
        assert layout.name > len("prompt-toolkit")
