from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from distlift.errors import ManifestUpdateError


def read_package_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc


def get_package_version(data: dict[str, Any]) -> str | None:
    return data.get("version")


def set_package_version(path: Path, version: str) -> None:
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
