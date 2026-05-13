from __future__ import annotations

from pathlib import Path

import attrs


@attrs.define
class BuildArtifact:
    """A single built file ready to upload or publish.

    Attributes:
        path: Filesystem path to the wheel, sdist, or archive.
        kind: Short discriminator such as "wheel", "sdist", or "tgz".
    """

    path: Path
    kind: str  # e.g. "wheel", "sdist", "tgz"


@attrs.define
class PublishRequest:
    """Inputs for uploading a set of artifacts to a package index.

    Attributes:
        artifacts: Built files to pass to the publisher CLI.
        repository_url: Optional non-default index URL for twine-like tools.
        dry_run: When True, publishers skip network upload.
        extra_args: Additional CLI tokens appended to the publish command.
    """

    artifacts: list[BuildArtifact]
    repository_url: str | None = None
    dry_run: bool = False
    extra_args: list[str] = attrs.Factory(list)


@attrs.define
class PublishResult:
    """Outcome of a single publish attempt for one batch of artifacts.

    Attributes:
        success: True when every artifact in the batch uploaded successfully.
        artifacts: The artifacts that were part of this attempt.
        error: Tool stderr or message when success is False.
    """

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
        error: Set when publishing could not start (config or detection).
    """

    success: bool
    projects: list[tuple[str, PublishResult]] = attrs.Factory(list)
    error: str | None = None
