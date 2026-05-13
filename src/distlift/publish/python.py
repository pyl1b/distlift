from __future__ import annotations

import subprocess
from pathlib import Path

from distlift.errors import PublishError
from distlift.publish.models import BuildArtifact, PublishRequest, PublishResult


def build_python_distributions(
    project_root: Path,
    outdir: Path | None = None,
) -> list[BuildArtifact]:
    """Run `python -m build` and return the produced artifacts."""
    cmd = ["python", "-m", "build"]
    if outdir:
        cmd += ["--outdir", str(outdir)]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise PublishError(f"Build failed:\n{result.stderr}")

    dist_dir = outdir or (project_root / "dist")
    artifacts = []
    for path in sorted(dist_dir.glob("*")):
        if path.suffix == ".whl":
            artifacts.append(BuildArtifact(path=path, kind="wheel"))
        elif path.name.endswith(".tar.gz"):
            artifacts.append(BuildArtifact(path=path, kind="sdist"))
    return artifacts


def publish_python_distributions(request: PublishRequest) -> PublishResult:
    """Upload artifacts with twine or uv publish."""
    cmd = ["python", "-m", "twine", "upload"]
    if request.repository_url:
        cmd += ["--repository-url", request.repository_url]
    if request.dry_run:
        return PublishResult(success=True, artifacts=request.artifacts)
    cmd += [str(a.path) for a in request.artifacts]
    cmd += request.extra_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return PublishResult(success=False, error=result.stderr)
    return PublishResult(success=True, artifacts=request.artifacts)
