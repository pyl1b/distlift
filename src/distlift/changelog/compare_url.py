"""Derive compare URL templates from configured Git remotes."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from distlift.logging_utils import get_logger

log = get_logger(__name__)

_GITHUB_SSH = re.compile(r"^git@github\.com:(?P<path>.+?)(?:\.git)?$")
_GITLAB_SSH = re.compile(r"^git@gitlab\.com:(?P<path>.+?)(?:\.git)?$")
_BITBUCKET_SSH = re.compile(r"^git@bitbucket\.org:(?P<path>.+?)(?:\.git)?$")


def derive_compare_url_template(remote_url: str) -> str | None:
    """Return a ``{prev}`` / ``{next}`` compare URL template when recognized.

    Args:
        remote_url: Output of ``git remote get-url`` for a single remote.
    """
    raw = remote_url.strip()

    if not raw:
        return None

    gh_ssh = _GITHUB_SSH.match(raw)

    if gh_ssh:
        path = gh_ssh.group("path")

        return f"https://github.com/{path}/compare/{{prev}}...{{next}}"

    gl_ssh = _GITLAB_SSH.match(raw)

    if gl_ssh:
        path = gl_ssh.group("path")

        return f"https://gitlab.com/{path}/-/compare/{{prev}}...{{next}}"

    bb_ssh = _BITBUCKET_SSH.match(raw)

    if bb_ssh:
        path = bb_ssh.group("path")

        return (
            f"https://bitbucket.org/{path}/branches/compare/{{next}}..{{prev}}"
        )

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        host = parsed.hostname or ""
        path = parsed.path.strip("/")

        if path.endswith(".git"):
            path = path[:-4]

        if "github.com" in host:
            return f"https://github.com/{path}/compare/{{prev}}...{{next}}"

        if "gitlab.com" in host:
            return f"https://gitlab.com/{path}/-/compare/{{prev}}...{{next}}"

        if "bitbucket.org" in host:
            return (
                f"https://bitbucket.org/{path}/branches/compare/"
                f"{{next}}..{{prev}}"
            )

    log.debug("Unrecognized git remote URL host or scheme: %s", raw[:120])

    return None


def resolve_compare_url_template(
    explicit_template: str,
    remote_url: str | None,
) -> str | None:
    """Pick an effective compare template from config or remote detection.

    Args:
        explicit_template: Non-empty configured template text, or empty.
        remote_url: Optional resolved remote URL when explicit is blank.
    """
    trimmed = explicit_template.strip()

    if trimmed:
        return trimmed

    if remote_url:
        return derive_compare_url_template(remote_url)

    return None
