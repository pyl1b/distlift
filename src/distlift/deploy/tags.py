"""Compute the next numbered deploy marker tag for a Git prefix."""

from __future__ import annotations

import re


def next_deploy_tag_name(
    existing_tags: list[str],
    tag_prefix: str,
) -> str:
    r"""Return the next tag name ``{tag_prefix}_{N}`` from existing local tags.

    Scans ``existing_tags`` for names matching ``^{tag_prefix}_(\d+)$`` (using
    a regex-escaped prefix), takes the maximum ``N``, and returns
    ``{tag_prefix}_{N+1}``. When no such tag exists, returns
    ``{tag_prefix}_1``.

    Args:
        existing_tags: Tag names from ``git tag --list`` (any order).
        tag_prefix: Configured prefix (already validated for safe characters).
    """
    escaped = re.escape(tag_prefix)
    pattern = re.compile(rf"^{escaped}_(\d+)$")
    highest = 0

    for name in existing_tags:
        match = pattern.match(name)

        if match is None:
            continue

        highest = max(highest, int(match.group(1)))

    return f"{tag_prefix}_{highest + 1}"
