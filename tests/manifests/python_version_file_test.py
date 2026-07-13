"""Tests for Python ``__version__`` manifest helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from distlift.errors import ManifestUpdateError
from distlift.manifests.handler import get_handler
from distlift.manifests.python_version_file import (
    read_python_version,
    set_python_version,
)

_SAMPLE_VERSION = '''\
"""Package version."""

__version__ = "0.1.1"
'''


class TestPythonVersionFile:
    """Python version file helpers."""

    def test_read_python_version(self, tmp_path: Path) -> None:
        """Parse version from a standard ``__version__.py`` file."""
        path = tmp_path / "__version__.py"
        path.write_text(_SAMPLE_VERSION, encoding="utf-8")
        assert read_python_version(path) == "0.1.1"

    def test_set_python_version_preserves_other_lines(
        self, tmp_path: Path
    ) -> None:
        """Update only the ``__version__`` line."""
        path = tmp_path / "__version__.py"
        path.write_text(_SAMPLE_VERSION, encoding="utf-8")
        set_python_version(path, "0.1.2")
        text = path.read_text(encoding="utf-8")
        assert '"""Package version."""' in text
        assert '__version__ = "0.1.2"' in text
        assert read_python_version(path) == "0.1.2"

    def test_set_python_version_missing_line_raises(
        self, tmp_path: Path
    ) -> None:
        """Reject Python files without a version assignment."""
        path = tmp_path / "__version__.py"
        path.write_text('VALUE = "demo"\n', encoding="utf-8")
        with pytest.raises(ManifestUpdateError):
            set_python_version(path, "1.0.0")


class TestPythonVersionHandler:
    """Built-in ``python-version`` manifest handler."""

    def test_handler_round_trip(self, tmp_path: Path) -> None:
        """Registered handler reads and writes Python version files."""
        handler = get_handler("python-version")
        assert handler is not None
        path = tmp_path / "__version__.py"
        path.write_text(_SAMPLE_VERSION, encoding="utf-8")
        assert handler.read_version(path) == "0.1.1"
        handler.write_version(path, "2.0.0")
        assert handler.read_version(path) == "2.0.0"
