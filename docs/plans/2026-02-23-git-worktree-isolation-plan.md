# Git Worktree Isolation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Protect developer in-progress work by using git worktrees for CFIT agent sessions instead of `git checkout`.

**Architecture:** New `src/worktree.py` module handles cleanup. The agent prompt is updated with worktree instructions and guardrails. Launcher functions call cleanup after agent finishes.

**Tech Stack:** Python 3.11, subprocess (git CLI), shutil (fallback cleanup)

---

### Task 1: Create `src/worktree.py` — `cleanup_worktrees()`

**Files:**
- Create: `src/worktree.py`
- Create: `tests/test_worktree.py`

**Step 1: Write the failing test**

Create `tests/__init__.py` and `tests/test_worktree.py`:

```python
# tests/__init__.py
# (empty)
```

```python
# tests/test_worktree.py
import subprocess
from pathlib import Path

from src.worktree import cleanup_worktrees


def test_cleanup_removes_existing_worktree(tmp_path):
    """cleanup_worktrees removes a worktree created for a CFIT task."""
    # Set up a real git repo with a worktree
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worktree.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.worktree'`

**Step 3: Write minimal implementation**

```python
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
        wt_path = Path(repo_path) / repo_name / ".worktrees" / f"cfit-{task_id}"
        if not wt_path.exists():
            continue

        repo_dir = Path(repo_path) / repo_name
        print(f">>> Cleaning up worktree: {wt_path}")

        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt_path)],
                cwd=repo_dir,
                capture_output=True,
                check=True,
            )
            print(f">>> Worktree removed: {wt_path}")
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
            except Exception as fallback_err:
                print(f">>> Worktree cleanup fallback also failed: {fallback_err}")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_worktree.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/worktree.py tests/__init__.py tests/test_worktree.py
git commit -m "feat: add worktree cleanup module with tests"
```

---

### Task 2: Add `list_worktrees()` utility

**Files:**
- Modify: `src/worktree.py`
- Modify: `tests/test_worktree.py`

**Step 1: Write the failing test**

Add to `tests/test_worktree.py`:

```python
from src.worktree import list_worktrees


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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worktree.py::test_list_worktrees_shows_active -v`
Expected: FAIL — `ImportError: cannot import name 'list_worktrees'`

**Step 3: Write minimal implementation**

Add to `src/worktree.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_worktree.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/worktree.py tests/test_worktree.py
git commit -m "feat: add list_worktrees utility"
```

---

### Task 3: Update `build_prompt()` with worktree instructions and guardrails

**Files:**
- Modify: `src/agent_launcher.py:47-92` (the `build_prompt()` function)

**Step 1: Write the failing test**

Add to `tests/test_worktree.py`:

```python
from src.agent_launcher import build_prompt


def test_prompt_contains_worktree_instructions():
    """build_prompt includes git worktree instructions, not git checkout."""
    task_info = {
        "id": "123456",
        "title": "Test bug",
        "description": "Something is broken",
        "url": "https://app.asana.com/0/project/123456",
    }
    prompt = build_prompt(task_info, [])

    assert "git worktree add" in prompt
    assert "CRITICAL RULES" in prompt
    assert "NEVER run git checkout" in prompt
    # The old checkout instruction should be gone
    assert "git checkout -b" not in prompt
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worktree.py::test_prompt_contains_worktree_instructions -v`
Expected: FAIL — `assert "git worktree add" in prompt` (the current prompt has `git checkout -b`)

**Step 3: Modify `build_prompt()` in `src/agent_launcher.py`**

Replace lines 47-92 of `build_prompt()`. The returned string changes in two places:

**A) Add a CRITICAL RULES section** right after the `## Instructions` header:

```python
        f"## CRITICAL RULES\n"
        f"- NEVER run `git checkout`, `git switch`, or `git stash` in the main working directory\n"
        f"- ALWAYS use `git worktree add` to create an isolated copy for your changes\n"
        f"- The main repo directories are READ-ONLY for investigation — all file edits go in the worktree\n\n"
```

**B) Replace step 6** (lines 66-71) with:

```python
        f"6. Create an isolated worktree for your changes (do NOT run git checkout in the main repo):\n"
        f"   - `cd` into the affected repo's root directory\n"
        f"   - `mkdir -p .worktrees`\n"
        f"   - `git worktree add .worktrees/cfit-{task_info['id']} -b fix/cfit-{task_info['id']}`\n"
        f"   - `cd .worktrees/cfit-{task_info['id']}`\n"
        f"   - Make ALL code changes inside this worktree directory\n"
        f"   - Commit your changes, push the branch, and open a PR with `gh pr create`\n"
        f"   - PR title should reference the bug title\n"
        f"   - PR description should include the root cause and what was changed\n\n"
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_worktree.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add src/agent_launcher.py tests/test_worktree.py
git commit -m "feat: replace git checkout with worktree instructions in agent prompt"
```

---

### Task 4: Add cleanup calls to `launch_claude()` and `launch_cursor()`

**Files:**
- Modify: `src/agent_launcher.py:95-109` (`launch_claude()`) and `src/agent_launcher.py:228-364` (`launch_cursor()`)

**Step 1: Modify `launch_claude()`**

After `subprocess.run(cmd, cwd=repo_path)` on line 109, add:

```python
    from src.worktree import cleanup_worktrees
    cleanup_worktrees(repo_path, str(task_info["id"]), INVESTIGATION_REPOS or [Path(repo_path).name])
```

**Step 2: Modify `launch_cursor()`**

After `_wait_and_post_findings(task_info["id"])` on line 364, add:

```python
    from src.worktree import cleanup_worktrees
    cleanup_worktrees(repo_path, str(task_info["id"]), INVESTIGATION_REPOS or [Path(repo_path).name])
```

**Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: 6 passed

**Step 4: Commit**

```bash
git add src/agent_launcher.py
git commit -m "feat: add worktree cleanup after agent finishes"
```

---

### Task 5: Install pytest and verify full test suite

**Step 1: Install pytest in the project venv**

Run: `pip install pytest`

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: 6 passed

**Step 3: Commit (nothing to commit — just verification)**

---

### Task 6: Manual smoke test

**Step 1: Test worktree creation manually**

In any investigation repo (e.g., `~/workspace/hibob`):

```bash
mkdir -p .worktrees
git worktree add .worktrees/cfit-test-123 -b fix/cfit-test-123
ls .worktrees/cfit-test-123/   # Should show repo contents
```

**Step 2: Test cleanup**

```bash
python -c "from src.worktree import cleanup_worktrees; cleanup_worktrees('$HOME/workspace', 'test-123', ['hibob'])"
ls ~/workspace/hibob/.worktrees/   # cfit-test-123 should be gone
```

**Step 3: Test prompt output**

```bash
python -c "
from src.agent_launcher import build_prompt
p = build_prompt({'id': '999', 'title': 'Test', 'description': 'Desc', 'url': 'http://x'}, [])
print(p[:1500])
"
```

Verify: output contains `git worktree add`, `CRITICAL RULES`, no `git checkout -b`.

**Step 4: Final commit with all changes**

```bash
git add -A
git status  # Verify only expected files
git commit -m "feat: git worktree isolation for CFIT agent sessions

Prevents destruction of developer in-progress work by using git worktrees
instead of git checkout when agents create fix branches."
```
