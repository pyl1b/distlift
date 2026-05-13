from __future__ import annotations

import subprocess
from pathlib import Path

from distlift.errors import PublishError
from distlift.publish.models import (
    BuildArtifact,
    PublishRequest,
    PublishResult,
)


def build_javascript_distributions(
    project_root: Path,
    package_manager: str = "npm",
) -> list[BuildArtifact]:
    """Pack the JavaScript project into ``dist/*.tgz`` using the given PM.

    Args:
        project_root: Directory containing ``package.json``.
        package_manager: One of ``npm``, ``pnpm``, or ``yarn``.
    """
    if package_manager == "npm":
        cmd = ["npm", "pack", "--pack-destination", str(project_root / "dist")]
    elif package_manager == "pnpm":
        cmd = ["pnpm", "pack", "--out-dir", str(project_root / "dist")]
    elif package_manager == "yarn":
        cmd = [
            "yarn",
            "pack",
            "--out",
            str(project_root / "dist" / "package.tgz"),
        ]
    else:
        raise PublishError(f"Unsupported package manager: {package_manager}")

    (project_root / "dist").mkdir(exist_ok=True)
    result = subprocess.run(
        cmd, cwd=project_root, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise PublishError(f"Pack failed:\n{result.stderr}")

    artifacts = [
        BuildArtifact(path=p, kind="tgz")
        for p in sorted((project_root / "dist").glob("*.tgz"))
    ]
    return artifacts


def publish_javascript_distributions(
    request: PublishRequest,
    package_manager: str = "npm",
) -> PublishResult:
    """Publish each artifact with ``npm publish`` or an equivalent command.

    Args:
        request: Artifacts and flags; dry-run skips all subprocess calls.
        package_manager: One of ``npm``, ``pnpm``, or ``yarn``.
    """
    if request.dry_run:
        return PublishResult(success=True, artifacts=request.artifacts)

    for artifact in request.artifacts:
        if package_manager == "npm":
            cmd = ["npm", "publish", str(artifact.path)]
        elif package_manager == "pnpm":
            cmd = ["pnpm", "publish", str(artifact.path)]
        elif package_manager == "yarn":
            cmd = ["yarn", "publish", str(artifact.path)]
        else:
            return PublishResult(
                success=False,
                error=f"Unsupported package manager: {package_manager}",
            )
        cmd += request.extra_args
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return PublishResult(success=False, error=result.stderr)

    return PublishResult(success=True, artifacts=request.artifacts)
