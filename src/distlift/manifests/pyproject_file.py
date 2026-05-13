"""Read and write ``pyproject.toml`` metadata with format preservation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit

from distlift.errors import ManifestUpdateError


def read_pyproject(path: Path) -> dict[str, Any]:
    """Parse ``pyproject.toml`` at ``path`` into a plain dict tree.

    Args:
        path: Location of the TOML file.

    Raises:
        ManifestUpdateError: When the file cannot be read or parsed.
    """
    try:
        text = path.read_text(encoding="utf-8")

        return tomlkit.loads(text)  # type: ignore[return-value]
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc


def project_uses_dynamic_version(data: dict[str, Any]) -> bool:
    """Return True when ``[project].dynamic`` lists ``version``.

    Args:
        data: Parsed ``pyproject.toml`` document as a mapping.
    """
    dynamic = data.get("project", {}).get("dynamic", [])
    return "version" in dynamic


def get_project_version(data: dict[str, Any]) -> str | None:
    """Return ``project.version`` from parsed pyproject data, if present.

    Args:
        data: Parsed ``pyproject.toml`` document as a mapping.
    """
    return data.get("project", {}).get("version")


def get_project_name(data: dict[str, Any]) -> str | None:
    """Return ``project.name`` from parsed pyproject data, if present.

    Args:
        data: Parsed ``pyproject.toml`` document as a mapping.
    """
    raw = data.get("project", {}).get("name")

    if raw is None:
        return None

    name = str(raw).strip()

    return name or None


def set_project_version(path: Path, version: str) -> None:
    """Set ``project.version`` in ``path`` using format-preserving TOML writes.

    Args:
        path: ``pyproject.toml`` file to update.
        version: Semantic version string to persist.

    Raises:
        ManifestUpdateError: When the file is missing ``[project]``, uses a
            dynamic version, or cannot be read or written.
    """
    try:
        content = path.read_text(encoding="utf-8")
        doc = tomlkit.loads(content)
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    if "project" not in doc:
        raise ManifestUpdateError(
            f"pyproject.toml at {path} has no [project] section"
        )

    if project_uses_dynamic_version(doc):  # type: ignore[arg-type]
        raise ManifestUpdateError(
            f"{path} uses dynamic version; cannot set version directly"
        )

    doc["project"]["version"] = version  # type: ignore[index]

    try:
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc
