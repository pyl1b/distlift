"""Read and write ``package.json`` version fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from distlift.errors import ManifestUpdateError


def read_package_json(path: Path) -> dict[str, Any]:
    """Parse ``package.json`` at ``path``.

    Args:
        path: Location of the JSON manifest.

    Raises:
        ManifestUpdateError: When the file cannot be read or is not valid JSON.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc


def get_package_name(data: dict[str, Any]) -> str | None:
    """Return the ``name`` field from parsed package data, if present.

    Args:
        data: Parsed ``package.json`` object (mapping).
    """
    raw = data.get("name")

    if raw is None:
        return None

    name = str(raw).strip()

    return name or None


def get_package_version(data: dict[str, Any]) -> str | None:
    """Return the ``version`` field from parsed package data, if present.

    Args:
        data: Parsed ``package.json`` object (mapping).
    """
    return data.get("version")


def set_package_version(path: Path, version: str) -> None:
    """Write ``version`` into ``path`` with stable JSON formatting.

    Args:
        path: ``package.json`` file to update.
        version: Version string to persist.

    Raises:
        ManifestUpdateError: When the file cannot be read or written.
    """
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    data["version"] = version

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc
