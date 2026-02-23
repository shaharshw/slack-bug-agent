# tests/test_worktree.py
import subprocess
from pathlib import Path

from src.worktree import cleanup_worktrees, list_worktrees


def test_cleanup_removes_existing_worktree(tmp_path):
    """cleanup_worktrees removes a worktree created for a CFIT task."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, capture_output=True, check=True)

    wt_dir = repo / ".worktrees"
    wt_dir.mkdir()
    wt_path = wt_dir / "cfit-123"
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", "fix/cfit-123"],
        cwd=repo, capture_output=True, check=True,
    )
    assert wt_path.exists()

    cleanup_worktrees(str(tmp_path), "123", ["myrepo"])

    assert not wt_path.exists()

    # Verify the branch was also deleted
    result = subprocess.run(
        ["git", "branch", "--list", "fix/cfit-123"],
        cwd=repo, capture_output=True, text=True,
    )
    assert result.stdout.strip() == ""


def test_cleanup_skips_missing_worktree(tmp_path):
    """cleanup_worktrees does nothing when the worktree doesn't exist."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)

    # Should not raise
    cleanup_worktrees(str(tmp_path), "999", ["myrepo"])


def test_cleanup_fallback_shutil(tmp_path):
    """cleanup_worktrees falls back to shutil.rmtree when git command fails."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)

    # Create a fake worktree directory (not a real git worktree)
    wt_path = repo / ".worktrees" / "cfit-456"
    wt_path.mkdir(parents=True)
    (wt_path / "somefile.txt").write_text("dirty")

    cleanup_worktrees(str(tmp_path), "456", ["myrepo"])

    assert not wt_path.exists()


def test_cleanup_handles_multiple_repos(tmp_path):
    """cleanup_worktrees processes multiple repos; one with worktree, one without."""
    # Repo A: has a worktree
    repo_a = tmp_path / "repo_a"
    repo_a.mkdir()
    subprocess.run(["git", "init"], cwd=repo_a, capture_output=True, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo_a, capture_output=True, check=True)
    wt_dir = repo_a / ".worktrees"
    wt_dir.mkdir()
    wt_path = wt_dir / "cfit-555"
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", "fix/cfit-555"],
        cwd=repo_a, capture_output=True, check=True,
    )

    # Repo B: no worktree
    repo_b = tmp_path / "repo_b"
    repo_b.mkdir()
    subprocess.run(["git", "init"], cwd=repo_b, capture_output=True, check=True)

    cleanup_worktrees(str(tmp_path), "555", ["repo_a", "repo_b"])

    assert not wt_path.exists()


def test_list_worktrees_shows_active(tmp_path):
    """list_worktrees returns paths of active worktrees for CFIT tasks."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, capture_output=True, check=True)

    wt_dir = repo / ".worktrees"
    wt_dir.mkdir()
    wt_path = wt_dir / "cfit-789"
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "-b", "fix/cfit-789"],
        cwd=repo, capture_output=True, check=True,
    )

    result = list_worktrees(str(tmp_path), ["myrepo"])
    assert len(result) == 1
    assert result[0] == str(wt_path)


def test_list_worktrees_empty(tmp_path):
    """list_worktrees returns empty list when no CFIT worktrees exist."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)

    result = list_worktrees(str(tmp_path), ["myrepo"])
    assert result == []
