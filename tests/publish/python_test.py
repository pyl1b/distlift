from pathlib import Path

from distlift.publish.models import BuildArtifact, PublishRequest
from distlift.publish.python import publish_python_distributions


class TestPublishPythonDryRun:
    def test_dry_run_returns_success(self, tmp_path: Path):
        artifact = BuildArtifact(path=tmp_path / "pkg-1.0.0.whl", kind="wheel")
        request = PublishRequest(artifacts=[artifact], dry_run=True)
        result = publish_python_distributions(request)
        assert result.success
        assert result.artifacts == [artifact]
