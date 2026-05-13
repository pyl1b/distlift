from __future__ import annotations

import attrs

from distlift.config.models import BumpKind, VersionFormat


@attrs.define(frozen=True)
class VersionParts:
    major: int
    minor: int = 0
    patch: int = 0
    fmt: VersionFormat = VersionFormat.MAJOR_MINOR_PATCH

    def __str__(self) -> str:
        from distlift.versioning.formatter import format_version

        return format_version(self)


@attrs.define(frozen=True)
class VersionSelection:
    bump: BumpKind | None = None
    explicit: str | None = None

    def is_explicit(self) -> bool:
        return self.explicit is not None


@attrs.define(frozen=True)
class ResolvedVersion:
    current: VersionParts
    next: VersionParts
    tag_name: str
    bump: BumpKind | None
    was_explicit: bool
