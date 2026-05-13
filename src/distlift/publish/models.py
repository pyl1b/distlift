from __future__ import annotations

from pathlib import Path

import attrs


@attrs.define
class BuildArtifact:
    path: Path
    kind: str  # e.g. "wheel", "sdist", "tgz"


@attrs.define
class PublishRequest:
    artifacts: list[BuildArtifact]
    repository_url: str | None = None
    dry_run: bool = False
    extra_args: list[str] = attrs.Factory(list)


@attrs.define
class PublishResult:
    success: bool
    artifacts: list[BuildArtifact] = attrs.Factory(list)
    error: str | None = None


@attrs.define
class PublishRunResult:
    """Outcome of publishing one or more local projects.

    Attributes:
        success: True when every targeted project published successfully.
        projects: Pairs of a display label (e.g. package name) and publish
            result per project root.
        error: Set when publishing could not start (configuration or detection).
    """

    success: bool
    projects: list[tuple[str, PublishResult]] = attrs.Factory(list)
    error: str | None = None
