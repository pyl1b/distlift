"""Read and write Python ``__version__`` module files."""

from __future__ import annotations

import re
from pathlib import Path

from distlift.errors import ManifestUpdateError

_VERSION_RE = re.compile(
    r'^(?P<prefix>\s*__version__\s*=\s*)(?P<quote>["\'])'
    r'(?P<version>[^"\']*)(?P=quote)(?P<suffix>\s*)$'
)


def read_python_version(path: Path) -> str | None:
    """Return the ``__version__`` assignment in a Python file.

    Args:
        path: Python file expected to contain ``__version__ = "..."``.

    Raises:
        ManifestUpdateError: When the file cannot be read.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    # Find the first top-level version assignment.
    for line in lines:
        match = _VERSION_RE.match(line)
        if match:
            return match.group("version")

    return None


def set_python_version(path: Path, version: str) -> None:
    """Set the ``__version__`` assignment in a Python file.

    Args:
        path: Python file expected to contain ``__version__ = "..."``.
        version: New version string to persist.

    Raises:
        ManifestUpdateError: When the file cannot be read, lacks a version
            assignment, or cannot be written.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    # Replace exactly one assignment and leave all other text untouched.
    replaced = False
    new_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        ending = ""
        body = line
        if line.endswith("\r\n"):
            body = line[:-2]
            ending = "\r\n"
        elif line.endswith("\n"):
            body = line[:-1]
            ending = "\n"

        match = _VERSION_RE.match(body)
        if match and not replaced:
            quote = match.group("quote")
            body = (
                f"{match.group('prefix')}{quote}{version}{quote}"
                f"{match.group('suffix')}"
            )
            replaced = True
        new_lines.append(body + ending)

    if not replaced:
        raise ManifestUpdateError(
            f"Python version file at {path} has no __version__ assignment"
        )

    try:
        path.write_text("".join(new_lines), encoding="utf-8")
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc
