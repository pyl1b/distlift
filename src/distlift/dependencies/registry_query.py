"""Query package registries for published versions."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from packaging.version import Version

from distlift.dependencies.upgrade_models import RegistryVersion
from distlift.errors import RegistryQueryError
from distlift.logging_utils import get_logger

log = get_logger(__name__)


def fetch_pip_versions(
    distribution_name: str,
    *,
    timeout_seconds: int,
) -> list[RegistryVersion]:
    """Return versions reported by ``pip index versions``.

    Args:
        distribution_name: PyPI distribution name.
        timeout_seconds: Subprocess timeout in seconds.
    """
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "index",
        "versions",
        distribution_name,
    ]

    log.log(1, "Running %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        raise RegistryQueryError(
            "pip index versions failed for {} (exit {}): {}".format(
                distribution_name,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    raw_versions = _parse_pip_versions_output(combined)
    return _sort_registry_versions(raw_versions)


def fetch_npm_versions(
    package_name: str,
    *,
    timeout_seconds: int,
) -> list[RegistryVersion]:
    """Return versions reported by ``npm view <name> versions --json``.

    Args:
        package_name: npm package name.
        timeout_seconds: Subprocess timeout in seconds.
    """
    cmd = ["npm", "view", package_name, "versions", "--json"]

    log.log(1, "Running %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        raise RegistryQueryError(
            "npm view failed for {} (exit {}): {}".format(
                package_name,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    raw_versions = _parse_npm_versions_json(result.stdout or "")
    return _sort_registry_versions(raw_versions)


def fetch_pnpm_versions(
    package_name: str,
    *,
    timeout_seconds: int,
) -> list[RegistryVersion]:
    """Return versions reported by ``pnpm view``.

    Args:
        package_name: npm package name.
        timeout_seconds: Subprocess timeout in seconds.
    """
    cmd = ["pnpm", "view", package_name, "versions"]

    log.log(1, "Running %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        raise RegistryQueryError(
            "pnpm view failed for {} (exit {}): {}".format(
                package_name,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    raw_versions = _parse_plain_version_list(result.stdout or "")
    return _sort_registry_versions(raw_versions)


def fetch_yarn_versions(
    package_name: str,
    *,
    timeout_seconds: int,
) -> list[RegistryVersion]:
    """Return versions reported by ``yarn npm info``.

    Args:
        package_name: npm package name.
        timeout_seconds: Subprocess timeout in seconds.
    """
    cmd = ["yarn", "npm", "info", package_name, "versions", "--json"]

    log.log(1, "Running %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        cmd = ["npm", "view", package_name, "versions", "--json"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )

    if result.returncode != 0:
        raise RegistryQueryError(
            "yarn/npm view failed for {} (exit {}): {}".format(
                package_name,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    raw_versions = _parse_npm_versions_json(result.stdout or "")
    return _sort_registry_versions(raw_versions)


def _parse_pip_versions_output(combined: str) -> list[str]:
    """Parse version strings from pip index output.

    Args:
        combined: Merged stdout and stderr from pip.
    """
    versions_line = None

    for line in combined.splitlines():
        stripped = line.strip()

        if stripped.lower().startswith("available versions:"):
            versions_line = stripped
            break

    listed: list[str] = []

    if versions_line is not None:
        after_colon = versions_line.split(":", 1)[1]
        listed = [x.strip() for x in after_colon.split(",") if x.strip()]
    else:
        for line in combined.splitlines():
            inner = re.findall(r"\(([^)]+)\)", line)

            for chunk in inner:
                for part in chunk.split(","):
                    piece = part.strip()

                    if piece:
                        listed.append(piece)

            if listed:
                break

    return listed


def _parse_npm_versions_json(stdout: str) -> list[str]:
    """Parse npm JSON versions output into version strings.

    Args:
        stdout: Raw stdout from npm view.
    """
    text = stdout.strip()

    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _parse_plain_version_list(text)

    if isinstance(parsed, list):
        return [str(item) for item in parsed]

    if isinstance(parsed, str):
        return [parsed]

    return []


def _parse_plain_version_list(text: str) -> list[str]:
    """Parse comma- or newline-separated version lists.

    Args:
        text: Plain-text version listing.
    """
    if not text.strip():
        return []

    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]

    return [part.strip() for part in text.split(",") if part.strip()]


def _sort_registry_versions(raw_versions: list[str]) -> list[RegistryVersion]:
    """Sort versions newest-first and annotate prerelease metadata.

    Args:
        raw_versions: Version strings from a registry.
    """
    unique: dict[str, RegistryVersion] = {}

    for raw in raw_versions:
        try:
            parsed = Version(raw)
        except Exception:
            log.log(
                1,
                "Skipping unparsable registry version %r",
                raw,
                exc_info=True,
            )
            continue

        normalized = str(parsed)
        unique[normalized] = RegistryVersion(
            version=normalized,
            is_prerelease=bool(parsed.is_prerelease),
            is_yanked=False,
        )

    ordered = sorted(
        unique.values(), key=lambda v: Version(v.version), reverse=True
    )
    return ordered
