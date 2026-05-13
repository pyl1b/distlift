"""Locate distlift configuration files on disk and in pyproject.toml."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from distlift.constants import (
    DEFAULT_LOCAL_CONFIG_FILENAMES,
    DEFAULT_SYSTEM_CONFIG_PATHS,
    DEFAULT_USER_CONFIG_PATHS,
    PYPROJECT_TOOL_KEY,
)

logger = logging.getLogger(__name__)


def discover_local_config_paths(repo_root: Path) -> list[Path]:
    """Return existing local config file candidates under repo_root.

    Args:
        repo_root: Absolute path to the Git repository root directory.
    """
    return [
        repo_root / name
        for name in DEFAULT_LOCAL_CONFIG_FILENAMES
        if (repo_root / name).is_file()
    ]


def discover_user_config_paths() -> list[Path]:
    """Return existing user-level distlift configuration files."""
    return [p for p in DEFAULT_USER_CONFIG_PATHS if p.is_file()]


def discover_system_config_paths() -> list[Path]:
    """Return existing system-level distlift configuration files."""
    return [p for p in DEFAULT_SYSTEM_CONFIG_PATHS if p.is_file()]


def discover_embedded_pyproject_config(repo_root: Path) -> Path | None:
    """Return pyproject.toml path when it embeds a ``[tool.distlift]`` table.

    Args:
        repo_root: Absolute path to the Git repository root directory.
    """
    candidate = repo_root / "pyproject.toml"

    if not candidate.is_file():
        return None

    # Read and parse pyproject.toml to see whether distlift config exists
    try:
        with candidate.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        logger.debug(
            "Could not read or parse pyproject.toml for embedded distlift "
            "config at %s",
            candidate,
            exc_info=True,
        )
        return None

    if PYPROJECT_TOOL_KEY in data.get("tool", {}):
        return candidate

    return None
