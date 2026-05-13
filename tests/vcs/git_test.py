import subprocess
from pathlib import Path

import pytest

from distlift.errors import GitStateError
from distlift.vcs.git import GitRepository


class TestGitRepository:
    def test_clean_worktree_passes_on_clean_repo(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        repo.ensure_clean_worktree()  # should not raise

    def test_dirty_worktree_raises(self, tmp_git_repo: Path):
        (tmp_git_repo / "dirty.txt").write_text("untracked")
        # staged but uncommitted also counts as dirty
        subprocess.run(
            ["git", "add", "dirty.txt"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
        )
        repo = GitRepository(root=tmp_git_repo)
        with pytest.raises(GitStateError):
            repo.ensure_clean_worktree()

    def test_get_tags_empty(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        assert repo.get_tags() == []

    def test_create_and_list_tag(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        repo.create_tag("v1.0.0")
        assert "v1.0.0" in repo.get_tags()

    def test_tag_exists(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        assert not repo.tag_exists("v9.9.9")
        repo.create_tag("v9.9.9")
        assert repo.tag_exists("v9.9.9")

    def test_get_current_branch(self, tmp_git_repo: Path):
        repo = GitRepository(root=tmp_git_repo)
        branch = repo.get_current_branch()
        assert branch in ("main", "master")

    def test_commit_all(self, tmp_python_project: Path):
        repo = GitRepository(root=tmp_python_project)
        (tmp_python_project / "new_file.txt").write_text("hello")
        sha = repo.commit_all("chore: add file")
        assert len(sha) == 40
