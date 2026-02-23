import json
import subprocess
import time
from pathlib import Path

from src.agent_context import build_context_section
from src.config import AGENT_CONTEXT_FILES, INVESTIGATION_REPOS, OUTPUT_DIR
from src.guardrails import sanitize_task_content, redact_secrets, check_size_limit
from src.worktree import cleanup_worktrees


def _build_agent_context() -> str:
    """Build context section from configured agent context files."""
    if not AGENT_CONTEXT_FILES:
        return ""
    configs = [
        {"path": f, "name": Path(f).name, "type": "ai_context"}
        for f in AGENT_CONTEXT_FILES
        if Path(f).is_file()
    ]
    return build_context_section(configs)


def build_prompt(task_info: dict, attachment_paths: list[str]) -> str:
    attachments_section = ""
    if attachment_paths:
        file_list = "\n".join(f"- {p}" for p in attachment_paths)
        attachments_section = f"\n## Attachments\n{file_list}\n"

    custom_fields_section = ""
    if task_info.get("custom_fields"):
        fields = "\n".join(
            f"- **{k}:** {v}" for k, v in task_info["custom_fields"].items() if v
        )
        if fields:
            custom_fields_section = f"\n## Custom Fields\n{fields}\n"

    description = sanitize_task_content(task_info['description'])
    title = sanitize_task_content(task_info['title'])
    url = task_info['url']
    due = task_info.get('due_date') or 'Not set'
    assignee = task_info.get('assignee_email') or task_info.get('assignee_name') or 'Unassigned'
    tags = ', '.join(task_info.get('tags', [])) or 'None'

    task_dir = Path(OUTPUT_DIR) / str(task_info["id"])
    findings_path = task_dir / "findings.md"
    summary_path = task_dir / "summary.txt"

    return (
        f"Investigate this CFIT bug and propose a solution.\n\n"
        f"## Bug Report\n"
        f"- **Title:** {title}\n"
        f"- **Asana:** {url}\n"
        f"- **Due:** {due}\n"
        f"- **Assignee:** {assignee}\n"
        f"- **Tags:** {tags}\n\n"
        f"## Description\n"
        f"<user-provided-content>\n{description}\n</user-provided-content>\n"
        f"{custom_fields_section}{attachments_section}\n"
        f"{'## Scope — Only investigate these repos' + chr(10) + ', '.join(f'`{r}/`' for r in INVESTIGATION_REPOS) + chr(10) + 'Do NOT search outside these directories.' + chr(10) + chr(10) if INVESTIGATION_REPOS else ''}"
        f"{_build_agent_context()}"
        f"## CRITICAL RULES\n"
        f"- NEVER run `git checkout`, `git switch`, or `git stash` in the main working directory\n"
        f"- ALWAYS use `git worktree add` to create an isolated copy for your changes\n"
        f"- The main repo directories are READ-ONLY for investigation — all file edits go in the worktree\n\n"
        f"## Instructions\n"
        f"1. Analyze the bug description and any attached screenshots\n"
        f"2. Search the codebase for relevant code paths{' (only in: ' + ', '.join(INVESTIGATION_REPOS) + ')' if INVESTIGATION_REPOS else ''}\n"
        f"3. Identify the root cause\n"
        f"4. Create an isolated worktree for your changes (do NOT run `git checkout` in the main repo):\n"
        f"   - `cd` into the affected repo's root directory\n"
        f"   - `mkdir -p .worktrees && echo '.worktrees/' >> .gitignore` (if not already in .gitignore)\n"
        f"   - `git worktree add .worktrees/cfit-{task_info['id']} -b fix/cfit-{task_info['id']}`\n"
        f"   - `cd .worktrees/cfit-{task_info['id']}`\n"
        f"   - All remaining steps happen inside this worktree directory\n"
        f"5. Implement the fix — write the actual code changes\n"
        f"6. Write tests for the fix\n"
        f"7. Commit your changes, push the branch, and open a PR with `gh pr create`\n"
        f"   - PR title should reference the bug title\n"
        f"   - PR description should include the root cause and what was changed\n\n"
        f"## IMPORTANT: Write your output to these two files\n\n"
        f"### 1. Summary (will be posted as an Asana comment)\n"
        f"Write a concise plain-text summary to:\n"
        f"`{summary_path}`\n\n"
        f"The summary should be short and readable, structured as:\n"
        f"- Root Cause: 2-3 sentences explaining what causes the bug\n"
        f"- Affected Code: which file(s) and function(s) are involved\n"
        f"- Fix Applied: what was changed and in which files\n"
        f"- PR: include the PR URL\n"
        f"- Reference: mention that full details with code samples and test plan are in the attached findings.md\n\n"
        f"### 2. Detailed findings (will be attached as a file)\n"
        f"Write your complete detailed findings to:\n"
        f"`{findings_path}`\n\n"
        f"The findings file must include:\n"
        f"- Root Cause: detailed explanation with error messages\n"
        f"- Affected Code: files, functions, line numbers\n"
        f"- Fix Applied: the actual code changes made with diffs\n"
        f"- PR URL: link to the pull request\n"
        f"- Test Plan: unit tests written and manual testing steps\n\n"
        f"IMPORTANT: Write the summary.txt file LAST, after everything else is complete (findings, code, PR).\n"
    )


def launch_claude(task_info: dict, attachment_paths: list[str], repo_path: str) -> None:
    prompt = build_prompt(task_info, attachment_paths)
    # Clean old output so the poll doesn't pick up stale results
    task_dir = Path(OUTPUT_DIR) / str(task_info["id"])
    for old_file in ("summary.txt", "findings.md"):
        (task_dir / old_file).unlink(missing_ok=True)
    task_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "claude",
        "-p", prompt,
        "--allowedTools", "Read,Grep,Glob,Task,Bash",
    ]
    print(f"\n>>> Launching Claude Code in {repo_path}")
    print(f">>> Task: {task_info['title']}")
    subprocess.run(cmd, cwd=repo_path)
    repos = INVESTIGATION_REPOS or [Path(repo_path).name]
    base = str(Path(repo_path).parent) if not INVESTIGATION_REPOS else repo_path
    cleanup_worktrees(base, str(task_info["id"]), repos)


def _is_cursor_running() -> bool:
    """Check if Cursor IDE is currently running."""
    result = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to (name of processes) contains "Cursor"'],
        capture_output=True, text=True,
    )
    return "true" in result.stdout.strip().lower()


def _get_cursor_window_title() -> str | None:
    """Get the title of the frontmost Cursor window."""
    result = subprocess.run(
        ["osascript", "-e", '''
            tell application "System Events"
                if exists (process "Cursor") then
                    tell process "Cursor"
                        if (count of windows) > 0 then
                            return name of window 1
                        end if
                    end tell
                end if
            end tell
            return ""
        '''],
        capture_output=True, text=True,
    )
    title = result.stdout.strip()
    return title if title else None


def _parse_workspace_from_title(title: str) -> str:
    """Extract the workspace/folder name from a Cursor window title.

    Title format examples:
      "folder_name — Cursor"
      "file.ts — folder_name — Cursor"
      "file.ts — my-workspace (Workspace) — Cursor"
    """
    parts = title.split(" \u2014 ")  # em-dash separator
    if len(parts) >= 2:
        return parts[-2].strip()
    return title.strip()


def _cursor_has_correct_workspace(repo_path: str, repos: list[str], workspace_file: str | None) -> bool:
    """Check if the current Cursor window has the correct workspace/repos open."""
    title = _get_cursor_window_title()
    if not title:
        return False

    ws_name = _parse_workspace_from_title(title)

    if not repos:
        # No specific repos — check if the target path folder name matches
        return ws_name == Path(repo_path).name

    if len(repos) == 1:
        return ws_name == repos[0]

    # Multi-repo: check against workspace file name
    if workspace_file:
        ws_stem = Path(workspace_file).stem
        expected = f"{ws_stem} (Workspace)"
        if ws_name == expected:
            return True

    return False


def _find_matching_workspace(repo_path: str, repos: list[str]) -> str | None:
    """Find an existing .code-workspace file whose folders match the target repos exactly."""
    target_paths = {str(Path(repo_path, r).resolve()) for r in repos}

    search_dirs = [
        repo_path,
        str(Path.home()),
        str(Path.home() / "Desktop"),
    ]

    for search_dir in search_dirs:
        d = Path(search_dir)
        if not d.is_dir():
            continue
        for ws_file in d.glob("*.code-workspace"):
            try:
                data = json.loads(ws_file.read_text())
                folders = data.get("folders", [])
                ws_paths = set()
                for folder in folders:
                    fp = folder.get("path", "")
                    resolved = (
                        Path(fp).resolve()
                        if Path(fp).is_absolute()
                        else (ws_file.parent / fp).resolve()
                    )
                    ws_paths.add(str(resolved))
                if ws_paths == target_paths:
                    return str(ws_file)
            except (json.JSONDecodeError, KeyError):
                continue
    return None


def _create_workspace_file(repo_path: str, repos: list[str]) -> str:
    """Create a .code-workspace file for the given repos."""
    folders = [{"path": str(Path(repo_path) / r)} for r in sorted(repos)]
    workspace_data = {"folders": folders, "settings": {}}

    ws_name = "-".join(sorted(repos))
    ws_path = Path(repo_path) / f"{ws_name}.code-workspace"
    ws_path.write_text(json.dumps(workspace_data, indent=2))
    print(f">>> Created workspace file: {ws_path}")
    return str(ws_path)


def launch_cursor(task_info: dict, attachment_paths: list[str], repo_path: str) -> None:
    prompt = build_prompt(task_info, attachment_paths)

    # Clean old output and write context file
    task_dir = Path(OUTPUT_DIR) / str(task_info["id"])
    for old_file in ("summary.txt", "findings.md"):
        (task_dir / old_file).unlink(missing_ok=True)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "cursor_prompt.md").write_text(prompt)

    print(f"\n>>> Launching Cursor agent for: {task_info['title']}")
    _CURSOR_CLI = "/Applications/Cursor.app/Contents/Resources/app/bin/cursor"
    repo_dirs = [str(Path(repo_path) / r) for r in INVESTIGATION_REPOS] if INVESTIGATION_REPOS else [repo_path]

    cursor_already_open = _is_cursor_running()

    # --- Workspace matching logic ---
    workspace_file = None
    need_to_open = False

    if not cursor_already_open:
        need_to_open = True
    else:
        # Cursor is running — check if the current workspace matches
        if INVESTIGATION_REPOS and len(INVESTIGATION_REPOS) > 1:
            workspace_file = _find_matching_workspace(repo_path, INVESTIGATION_REPOS)
        if _cursor_has_correct_workspace(repo_path, INVESTIGATION_REPOS, workspace_file):
            print(">>> Cursor already open with correct workspace — reusing")
        else:
            print(">>> Cursor is open but with a different workspace — switching...")
            need_to_open = True

    if need_to_open:
        if INVESTIGATION_REPOS and len(INVESTIGATION_REPOS) > 1:
            # Multi-repo: use a workspace file
            if not workspace_file:
                workspace_file = _find_matching_workspace(repo_path, INVESTIGATION_REPOS)
            if not workspace_file:
                workspace_file = _create_workspace_file(repo_path, INVESTIGATION_REPOS)
            print(f">>> Opening workspace: {workspace_file}")
            if cursor_already_open:
                subprocess.run([_CURSOR_CLI, "--new-window", workspace_file])
            else:
                subprocess.run(["open", "-a", "Cursor", workspace_file])
        else:
            # Single folder
            subprocess.run(["open", "-a", "Cursor", repo_dirs[0]])
        # Give the workspace time to load before interacting
        time.sleep(8)

    subprocess.run(["pbcopy"], input=prompt.encode(), check=True)

    print(">>> Opening new agent and pasting prompt...")
    result = subprocess.run(["osascript", "-e", '''
        -- Wait for Cursor to be running
        tell application "System Events"
            repeat 30 times
                if exists (process "Cursor") then exit repeat
                delay 1
            end repeat
        end tell

        -- Activate and bring to front
        tell application "Cursor" to activate
        delay 2
        tell application "System Events"
            tell process "Cursor"
                set frontmost to true
            end tell
        end tell
        delay 1

        -- Try up to 2 times: Cmd+I to open agent, paste, check if running
        set agentStarted to false
        repeat 2 times
            if agentStarted then exit repeat

            -- Cmd+I: always opens/focuses the Agent panel (never toggles closed)
            tell application "System Events"
                keystroke "i" using command down
            end tell
            delay 1.5

            -- Paste the prompt
            tell application "System Events"
                keystroke "v" using command down
            end tell
            delay 1

            -- Submit with Enter
            tell application "System Events"
                key code 36
            end tell
            delay 3

            -- Check if agent is running: look for a "Stop" button or a progress indicator
            -- If the window title changed or there is agent activity, we are good
            tell application "System Events"
                tell process "Cursor"
                    set allElems to entire contents of window 1
                    repeat with elem in allElems
                        try
                            set v to value of elem
                            if v is "Stop" or v is "Cancel" or v is "Generating" then
                                set agentStarted to true
                                exit repeat
                            end if
                        end try
                    end repeat
                end tell
            end tell

            if not agentStarted then
                -- Not started yet — wait and retry
                delay 2
            end if
        end repeat

        if agentStarted then
            return "ok"
        else
            return "ok:submitted"
        end if
    '''], capture_output=True, text=True)

    osascript_result = result.stdout.strip()
    if "ok:submitted" in osascript_result:
        print(f">>> Prompt submitted (could not confirm agent started — check Cursor)")
    else:
        print(f">>> Agent session started successfully")

    print(f">>> Task: {task_info['title']}")
    print(f">>> Cursor Agent is now investigating the bug")
    print(f">>> Watching for summary at: {OUTPUT_DIR}/{task_info['id']}/summary.txt")

    # Poll for the findings file and post to Asana when ready
    _wait_and_post_findings(task_info["id"])
    repos = INVESTIGATION_REPOS or [Path(repo_path).name]
    base = str(Path(repo_path).parent) if not INVESTIGATION_REPOS else repo_path
    cleanup_worktrees(base, str(task_info["id"]), repos)


def _wait_and_post_findings(task_id: str, poll_interval: int = 10, timeout: int = 1800) -> None:
    """Poll for summary.txt (or findings.md) and post results to Asana.

    Once findings.md appears, waits a grace period for summary.txt.
    If summary.txt never arrives, posts findings.md as fallback.
    """
    summary_path = Path(OUTPUT_DIR) / task_id / "summary.txt"
    findings_path = Path(OUTPUT_DIR) / task_id / "findings.md"
    elapsed = 0
    findings_seen_at: int | None = None  # elapsed time when findings.md first appeared
    findings_grace = 120  # seconds to wait for summary.txt after findings.md appears

    while elapsed < timeout:
        # Best case: summary.txt exists
        if summary_path.exists():
            time.sleep(5)  # let the file finish writing
            summary = summary_path.read_text().strip()
            if summary:
                _post_to_asana(task_id, summary, findings_path)
                return

        # Fallback: findings.md appeared but no summary.txt yet
        if findings_path.exists() and findings_seen_at is None:
            findings_seen_at = elapsed
            print(f">>> findings.md detected — waiting up to {findings_grace}s for summary.txt")

        if findings_seen_at is not None and (elapsed - findings_seen_at) >= findings_grace:
            findings_text = findings_path.read_text().strip()
            if findings_text:
                print(">>> summary.txt not written — posting findings.md as fallback")
                _post_to_asana(task_id, findings_text, findings_path)
                return

        time.sleep(poll_interval)
        elapsed += poll_interval
        if elapsed % 60 == 0:
            print(f">>> Still waiting for Cursor findings... ({elapsed // 60}m elapsed)")

    print(f">>> Timed out after {timeout // 60}m waiting for findings")
    # Last-ditch: post whatever exists
    if findings_path.exists():
        findings_text = findings_path.read_text().strip()
        if findings_text:
            print(">>> Posting findings.md after timeout")
            _post_to_asana(task_id, findings_text, findings_path)
            return
    print(f">>> You can manually post results later with: python -m src.main --post-results {task_id}")


def _post_to_asana(task_id: str, summary: str, findings_path: Path) -> None:
    """Post summary as comment and attach findings.md to the Asana task."""
    from src.asana_client import post_comment, upload_attachment

    print(f"\n>>> Findings detected! Posting to Asana task {task_id}...")

    # Apply output safety guardrails
    summary = redact_secrets(summary)
    summary = check_size_limit(summary, max_bytes=10240)

    # Post the summary as a comment
    comment = f"\U0001f916 AI Agent Investigation Results\n\n{summary}"
    try:
        post_comment(task_id, comment)
        print(">>> Summary posted as comment")
    except Exception as e:
        print(f">>> Error posting comment: {e}")

    # Attach findings.md with full details (redact secrets in file too)
    if findings_path.exists():
        findings_text = findings_path.read_text()
        redacted_findings = redact_secrets(findings_text)
        redacted_findings = check_size_limit(redacted_findings, max_bytes=512000)
        if redacted_findings != findings_text:
            findings_path.write_text(redacted_findings)
        try:
            upload_attachment(task_id, str(findings_path))
            print(">>> findings.md attached to task")
        except Exception as e:
            print(f">>> Error attaching findings.md: {e}")
            print(f">>> File saved locally at: {findings_path}")


def post_results(task_id: str) -> None:
    """Manually post findings to Asana for a given task ID."""
    summary_path = Path(OUTPUT_DIR) / task_id / "summary.txt"
    findings_path = Path(OUTPUT_DIR) / task_id / "findings.md"

    # Use summary if available, fall back to findings
    if summary_path.exists():
        summary = summary_path.read_text().strip()
    elif findings_path.exists():
        summary = findings_path.read_text().strip()
    else:
        print(f"No summary.txt or findings.md found in {OUTPUT_DIR}/{task_id}/")
        return

    if not summary:
        print("Summary/findings file is empty")
        return

    _post_to_asana(task_id, summary, findings_path)
    print(f">>> Done posting to Asana task {task_id}")


def launch(task_info: dict, attachment_paths: list[str], repo_path: str, mode: str = "claude") -> None:
    if mode == "cursor":
        launch_cursor(task_info, attachment_paths, repo_path)
    else:
        launch_claude(task_info, attachment_paths, repo_path)
