"""Read and write Synology SPK ``INFO`` version fields."""

from __future__ import annotations

import re
from pathlib import Path

from distlift.errors import ManifestUpdateError

_VERSION_LINE = re.compile(r'^version="([^"]*)"\s*$', re.MULTILINE)


def read_info_version(path: Path) -> str | None:
    """Return the ``version`` value from a Synology ``INFO`` file.

    Args:
        path: Location of the ``INFO`` manifest.

    Raises:
        ManifestUpdateError: When the file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    match = _VERSION_LINE.search(text)
    if match is None:
        return None
    return match.group(1)


def set_info_version(path: Path, version: str) -> None:
    """Replace the ``version="..."`` line in a Synology ``INFO`` file.

    Args:
        path: ``INFO`` file to update.
        version: New version string to persist.

    Raises:
        ManifestUpdateError: When the file lacks a version line or cannot be
            written.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    if _VERSION_LINE.search(text) is None:
        raise ManifestUpdateError(
            f'Cannot update {path}: missing version="..." line',
        )

    updated = _VERSION_LINE.sub(
        'version="' + version.replace('"', "") + '"',
        text,
        count=1,
    )

    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc
