"""Check that published package versions are visible on language registries."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from distlift.errors import DeployError
from distlift.logging_utils import get_logger
from distlift.manifests.package_json_file import read_package_json
from distlift.manifests.pyproject_file import get_project_name, read_pyproject

log = get_logger(__name__)


def resolve_package_manifest(manifest_path: Path, package_root: Path) -> Path:
    """Return absolute resolved manifest path for a package root.

    Args:
        manifest_path: Path from a ``ReleaseTarget`` (absolute or relative).
        package_root: Package root directory (``ReleaseTarget.root``).
    """
    if manifest_path.is_absolute():
        return manifest_path.resolve()

    return (package_root / manifest_path).resolve()


def python_distribution_name_and_version(
    manifest_path: Path,
    package_root: Path,
) -> tuple[str, str]:
    """Read PyPI distribution name and declared version from ``pyproject.toml``.

    Args:
        manifest_path: Path to ``pyproject.toml`` (as on the release target).
        package_root: Directory that anchors relative manifest paths.

    Raises:
        DeployError: When the name or version is missing or invalid.
    """
    path = resolve_package_manifest(manifest_path, package_root)
    data = read_pyproject(path)
    name = get_project_name(data)
    version = data.get("project", {}).get("version")

    if not name or not str(name).strip():
        raise DeployError(
            "pyproject.toml has no [project].name for index check"
        )

    if version is None or not str(version).strip():
        raise DeployError(
            "pyproject.toml has no static [project].version for index check; "
            "dynamic or tag-only versions are not supported for verify_indexes"
        )

    return str(name).strip(), str(version).strip()


def javascript_package_name_and_version(
    manifest_path: Path,
    package_root: Path,
) -> tuple[str, str]:
    """Read npm package name and version from ``package.json``.

    Args:
        manifest_path: Path to ``package.json`` (as on the release target).
        package_root: Directory that anchors relative manifest paths.

    Raises:
        DeployError: When the name or version is missing.
    """
    path = resolve_package_manifest(manifest_path, package_root)
    data = read_package_json(path)
    name = data.get("name")
    version = data.get("version")

    if not name or not str(name).strip():
        raise DeployError("package.json has no name for index check")

    if not version or not str(version).strip():
        raise DeployError("package.json has no version for index check")

    return str(name).strip(), str(version).strip()


def assert_python_version_on_index(
    distribution_name: str, version: str
) -> None:
    """Require ``version`` to appear among versions reported by ``pip index``.

    Uses ``sys.executable -m pip`` so the active interpreter and pip config
    (including extra indexes) apply.

    Args:
        distribution_name: Name on the index (``[project].name``).
        version: Exact version string that must be published.

    Raises:
        DeployError: When pip fails or the version is not listed.
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
    )

    if result.returncode != 0:
        raise DeployError(
            "pip index versions failed for {} (exit {}): {}".format(
                distribution_name,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
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
        # Fallback: parse parenthesized list on first line or scan for version tokens
        for line in combined.splitlines():
            inner = re.findall(r"\(([^)]+)\)", line)

            for chunk in inner:
                for part in chunk.split(","):
                    p = part.strip()

                    if p:
                        listed.append(p)

            if listed:
                break

    if version not in listed and versions_line is None:
        # Last resort: whole output contains exact version as a token
        if re.search(rf"\b{re.escape(version)}\b", combined):
            return

    if version not in listed:
        raise DeployError(
            "Version {} of {} not found among pip-reported versions: {}".format(
                version, distribution_name, listed or "(none parsed)"
            )
        )


def assert_javascript_version_on_registry(
    package_name: str, version: str
) -> None:
    """Require ``package_name@version`` to resolve via ``npm view``.

    Registry and auth follow npm configuration and environment.

    Args:
        package_name: Scoped or unscoped npm package name.
        version: Exact version that must exist on the registry.

    Raises:
        DeployError: When npm exits non-zero or reports another version.
    """
    spec = f"{package_name}@{version}"
    cmd = ["npm", "view", spec, "version"]

    log.log(1, "Running %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise DeployError(
            "npm view failed for {} (exit {}): {}".format(
                spec,
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        )

    reported = (result.stdout or "").strip()

    if reported != version:
        raise DeployError(
            f"npm view {spec} reported {reported!r} but expected {version!r}"
        )
