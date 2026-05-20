"""Format dependency autoupdate results for CLI output."""

from __future__ import annotations

from distlift.dependencies.models import (
    DependencyUpdateChange,
    DependencyUpdateResult,
)


def format_dependency_update_line(
    change: DependencyUpdateChange,
    *,
    dry_run: bool,
) -> str:
    """Format one dependency change as a single CLI line.

    Args:
        change: One dependency declaration change.
        dry_run: When True, use ``would update`` wording.
    """
    manifest_name = change.manifest_path.name
    verb = "would update" if dry_run else "updated"

    return (
        f"  {change.project_name}: {manifest_name} {verb} "
        f"{change.dependency_name} to {change.new_specifier}"
    )


def format_dependency_update_summary(
    results: list[DependencyUpdateResult],
    *,
    dry_run: bool,
    prefix: str = "",
) -> str | None:
    """Build a multi-line summary of dependency autoupdate results.

    Args:
        results: Results from all dependency updaters.
        dry_run: When True, prefix lines with dry-run style wording.
        prefix: Optional prefix for the header line (e.g. ``[dry-run] ``).

    Returns:
        Formatted text or ``None`` when there are no changes.
    """
    lines: list[str] = []

    for result in results:
        for change in result.changes:
            lines.append(
                format_dependency_update_line(change, dry_run=dry_run)
            )

    if not lines:
        return None

    header = f"{prefix}Autoupdated dependencies:"

    return header + "\n" + "\n".join(lines)
