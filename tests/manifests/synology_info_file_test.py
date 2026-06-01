"""Tests for Synology INFO manifest read/write helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from distlift.errors import ManifestUpdateError
from distlift.manifests.handler import get_handler
from distlift.manifests.synology_info_file import (
    read_info_version,
    set_info_version,
)

_SAMPLE_INFO = """\
package="srv-worker-node"
version="0.1.1"
displayname="srv-worker Worker Node"
"""


class TestSynologyInfoFile:
    """Synology INFO version helpers."""

    def test_read_info_version(self, tmp_path: Path) -> None:
        """Parse version from a standard INFO file."""
        path = tmp_path / "INFO"
        path.write_text(_SAMPLE_INFO, encoding="utf-8")
        assert read_info_version(path) == "0.1.1"

    def test_set_info_version_preserves_other_lines(
        self, tmp_path: Path
    ) -> None:
        """Update only the version line."""
        path = tmp_path / "INFO"
        path.write_text(_SAMPLE_INFO, encoding="utf-8")
        set_info_version(path, "0.1.2")
        text = path.read_text(encoding="utf-8")
        assert 'version="0.1.2"' in text
        assert 'package="srv-worker-node"' in text
        assert read_info_version(path) == "0.1.2"

    def test_set_info_version_missing_line_raises(
        self, tmp_path: Path
    ) -> None:
        """Reject INFO files without a version line."""
        path = tmp_path / "INFO"
        path.write_text('package="demo"\n', encoding="utf-8")
        with pytest.raises(ManifestUpdateError):
            set_info_version(path, "1.0.0")


class TestSynologyInfoHandler:
    """Built-in synology-info manifest handler."""

    def test_handler_round_trip(self, tmp_path: Path) -> None:
        """Register handler reads and writes INFO version."""
        handler = get_handler("synology-info")
        assert handler is not None
        path = tmp_path / "INFO"
        path.write_text(_SAMPLE_INFO, encoding="utf-8")
        assert handler.read_version(path) == "0.1.1"
        handler.write_version(path, "2.0.0")
        assert handler.read_version(path) == "2.0.0"
