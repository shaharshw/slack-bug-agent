# src/worktree.py
import shutil
import subprocess
from pathlib import Path


def cleanup_worktrees(repo_path: str, task_id: str, repos: list[str]) -> None:
    """Remove worktrees created for a CFIT task.

    Iterates over repos, removes .worktrees/cfit-{task_id} if it exists.
    Uses git worktree remove --force, falls back to shutil.rmtree.
    Never raises — cleanup failures are logged only.
    """
    for repo_name in repos:
        try:
            wt_path = Path(repo_path) / repo_name / ".worktrees" / f"cfit-{task_id}"
            if not wt_path.exists():
                continue

            repo_dir = Path(repo_path) / repo_name
            branch_name = f"fix/cfit-{task_id}"
            print(f">>> Cleaning up worktree: {wt_path}")

            removed = False
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(wt_path)],
                    cwd=repo_dir,
                    capture_output=True,
                    check=True,
                )
                print(f">>> Worktree removed: {wt_path}")
                removed = True
            except subprocess.CalledProcessError as e:
                print(f">>> git worktree remove failed: {e.stderr.decode().strip()}")
                try:
                    shutil.rmtree(wt_path)
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=repo_dir,
                        capture_output=True,
                    )
                    print(f">>> Worktree cleaned up via shutil fallback: {wt_path}")
                    removed = True
                except Exception as fallback_err:
                    print(f">>> Worktree cleanup fallback also failed: {fallback_err}")

            if removed:
                try:
                    subprocess.run(
                        ["git", "branch", "-D", branch_name],
                        cwd=repo_dir,
                        capture_output=True,
                        check=True,
                    )
                    print(f">>> Branch deleted: {branch_name}")
                except Exception as branch_err:
                    print(f">>> Branch deletion skipped: {branch_err}")
        except Exception as exc:
            print(f">>> Unexpected error during worktree cleanup for {repo_name}: {exc}")


def list_worktrees(repo_path: str, repos: list[str]) -> list[str]:
    """List active CFIT worktree paths across repos."""
    result = []
    for repo_name in repos:
        wt_dir = Path(repo_path) / repo_name / ".worktrees"
        if not wt_dir.exists():
            continue
        for child in sorted(wt_dir.iterdir()):
            if child.is_dir() and child.name.startswith("cfit-"):
                result.append(str(child))
    return result
