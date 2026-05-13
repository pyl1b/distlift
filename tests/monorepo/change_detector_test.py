import subprocess
from pathlib import Path

from distlift.config.models import (
    ManagedPackageConfig,
    VersionFormat,
    VersionSource,
)
from distlift.monorepo.change_detector import (
    find_package_last_tag,
    package_has_changes_since_tag,
)
from distlift.vcs.git import GitRepository


def _pkg(
    name: str = "pkgA", path: str = "packages/pkgA"
) -> ManagedPackageConfig:
    return ManagedPackageConfig(
        name=name,
        path=path,
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        version_source=VersionSource.MANIFEST,
    )


class TestFindPackageLastTag:
    def test_finds_tag_for_package(self):
        tags = ["v1.0.0-pkgA", "v0.5.0-pkgA", "v2.0.0-pkgB"]
        pkg = _pkg()
        result = find_package_last_tag(pkg, tags)
        assert result == "v1.0.0-pkgA"

    def test_returns_none_if_no_tag(self):
        pkg = _pkg()
        assert find_package_last_tag(pkg, []) is None


class TestPackageHasChangesSinceTag:
    def test_no_tag_means_changed(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        pkg = _pkg(path="packages/pkgA")
        assert package_has_changes_since_tag(pkg, None, repo)

    def test_no_changes_since_tag(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        repo.create_tag("v1.0.0-pkgA")
        pkg = _pkg(path="packages/pkgA")
        result = package_has_changes_since_tag(pkg, "v1.0.0-pkgA", repo)
        assert not result

    def test_change_in_package_path_detected(self, tmp_git_repo: Path):
        pkg_dir = tmp_git_repo / "packages" / "pkgA"
        pkg_dir.mkdir(parents=True)
        repo = GitRepository(root=tmp_git_repo)
        repo.create_tag("v1.0.0-pkgA")

        (pkg_dir / "src.py").write_text("x=1")
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "change pkg"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )

        pkg = _pkg(path="packages/pkgA")
        assert package_has_changes_since_tag(pkg, "v1.0.0-pkgA", repo)
