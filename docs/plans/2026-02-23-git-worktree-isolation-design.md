# Git Worktree Isolation for CFIT Agent

**Date:** 2026-02-23
**Problem:** When a new CFIT arrives while the developer has uncommitted changes on a branch, the agent's `git checkout -b` can fail or destroy work. No protection exists for in-progress work, and concurrent CFITs can conflict.

**Solution:** Use git worktrees so each CFIT investigation gets an isolated copy of the repo. The developer's working directory is never modified.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Which repos get worktrees | Only the affected repo | Agent investigates first (read-only), creates worktree only where changes are needed |
| Who creates the worktree | The agent, mid-investigation | Agent knows which repo is affected; launcher doesn't |
| Worktree location | `{repo}/.worktrees/cfit-{task_id}/` | Colocated with repo, easy to find, gitignored |
| Cleanup | Always auto-cleanup after agent finishes | Branch is on remote (PR exists); worktree is disposable |
| Concurrency | Concurrent — each CFIT in its own worktree | Main benefit of worktrees; existing threading model supports this |
| Cursor mode | Single window, agent uses terminal for git | Don't open new Cursor windows; agent creates worktree via integrated terminal |

## Components

### 1. New module: `src/worktree.py`

Cleanup-only module. The agent creates worktrees via prompt instructions; this module removes them after the agent finishes.

**Functions:**

- `cleanup_worktrees(repo_path: str, task_id: str, repos: list[str])` — Iterates over investigation repos, removes any worktree at `.worktrees/cfit-{task_id}`. Uses `git worktree remove --force`, falls back to `shutil.rmtree` + `git worktree prune`.

- `list_worktrees(repo_path: str, repos: list[str])` — Lists active worktrees across repos (debugging utility).

**Error handling:**
1. Worktree has uncommitted changes: `--force` flag (worktree is disposable)
2. Worktree doesn't exist: skip silently
3. Git command fails: catch error, fallback to `shutil.rmtree` + `git worktree prune`
4. Branch deletion fails: skip (branch is on remote)
5. Never crash the main task — cleanup failures are logged, not raised

### 2. Prompt changes in `build_prompt()`

Replace the current step 6 (`git checkout -b`) with worktree instructions.

**New step 6:**
```
6. Create an isolated worktree for your changes (do NOT checkout in the main repo):
   a. cd into the affected repo
   b. mkdir -p .worktrees
   c. git worktree add .worktrees/cfit-{task_id} -b fix/cfit-{task_id}
   d. cd .worktrees/cfit-{task_id}
   e. Make all code changes in the worktree
   f. Commit, push, and open a PR with gh pr create
```

**New critical rules section at top of prompt:**
```
## CRITICAL RULES
- NEVER run git checkout, git switch, or git stash in the main working directory
- ALWAYS use git worktree add to create an isolated copy for changes
- The main repo directories are READ-ONLY for investigation — all writes go in the worktree
```

**Post-agent validation guardrail:**
After the agent finishes, check if the main repo's branch or dirty state changed. Log a warning if so.

### 3. Integration into `agent_launcher.py`

**`launch_claude()`:**
- After `subprocess.run()` completes, call `cleanup_worktrees()`

**`launch_cursor()`:**
- After `_wait_and_post_findings()` completes, call `cleanup_worktrees()`
- No changes to Cursor window management — agent uses terminal for worktree commands

**No changes to `slack_listener.py`** — existing daemon thread model already supports concurrent CFITs.

## File Changes Summary

| File | Change |
|------|--------|
| `src/worktree.py` | New file — cleanup_worktrees(), list_worktrees() |
| `src/agent_launcher.py` | Update build_prompt() with worktree instructions + critical rules. Add cleanup calls in launch_claude() and launch_cursor() |

## Flow Diagram

```
CFIT arrives in Slack
    |
    v
Background thread spawns
    |
    v
Agent launches in main repo (READ-ONLY investigation)
    |
    v
Agent identifies affected repo (e.g., hibob)
    |
    v
Agent runs: git worktree add .worktrees/cfit-{id} -b fix/cfit-{id}
    |
    v
Agent cd's into worktree, makes changes, commits, pushes, opens PR
    |
    v
Agent writes summary.txt + findings.md
    |
    v
Launcher posts findings to Asana
    |
    v
cleanup_worktrees() removes worktree directory
    |
    v
Done — developer's main branch and changes are untouched
```
