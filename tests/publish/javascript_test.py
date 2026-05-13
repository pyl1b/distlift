from pathlib import Path

from distlift.publish.models import BuildArtifact, PublishRequest
from distlift.publish.javascript import publish_javascript_distributions


class TestPublishJavaScriptDryRun:
    def test_dry_run_returns_success(self, tmp_path: Path):
        artifact = BuildArtifact(path=tmp_path / "pkg-1.0.0.tgz", kind="tgz")
        request = PublishRequest(artifacts=[artifact], dry_run=True)
        result = publish_javascript_distributions(request)
        assert result.success
        assert result.artifacts == [artifact]
