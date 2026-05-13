from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit

from distlift.errors import ManifestUpdateError


def read_pyproject(path: Path) -> dict[str, Any]:
    try:
        return tomlkit.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc


def project_uses_dynamic_version(data: dict[str, Any]) -> bool:
    dynamic = data.get("project", {}).get("dynamic", [])
    return "version" in dynamic


def get_project_version(data: dict[str, Any]) -> str | None:
    return data.get("project", {}).get("version")


def set_project_version(path: Path, version: str) -> None:
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
