from __future__ import annotations

from pathlib import Path

from distlift.constants import (
    DEFAULT_LOCAL_CONFIG_FILENAMES,
    DEFAULT_SYSTEM_CONFIG_PATHS,
    DEFAULT_USER_CONFIG_PATHS,
    PYPROJECT_TOOL_KEY,
)


def discover_local_config_paths(repo_root: Path) -> list[Path]:
    """Return existing local config file candidates under repo_root."""
    return [
        repo_root / name
        for name in DEFAULT_LOCAL_CONFIG_FILENAMES
        if (repo_root / name).is_file()
    ]


def discover_user_config_paths() -> list[Path]:
    """Return existing user-level config files."""
    return [p for p in DEFAULT_USER_CONFIG_PATHS if p.is_file()]


def discover_system_config_paths() -> list[Path]:
    """Return existing system-level config files."""
    return [p for p in DEFAULT_SYSTEM_CONFIG_PATHS if p.is_file()]


def discover_embedded_pyproject_config(repo_root: Path) -> Path | None:
    """Return the repo pyproject.toml path if it contains [tool.distlift]."""
    candidate = repo_root / "pyproject.toml"
    if not candidate.is_file():
        return None

    try:
        import tomllib

        with candidate.open("rb") as fh:
            data = tomllib.load(fh)
        if PYPROJECT_TOOL_KEY in data.get("tool", {}):
            return candidate
    except Exception:
        pass
    return None
