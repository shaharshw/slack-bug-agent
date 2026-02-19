import subprocess
import time
from pathlib import Path

from src.agent_context import build_context_section
from src.config import AGENT_CONTEXT_FILES, INVESTIGATION_REPOS, OUTPUT_DIR


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

    description = task_info['description']
    title = task_info['title']
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
        f"{description}\n"
        f"{custom_fields_section}{attachments_section}\n"
        f"{'## Scope — Only investigate these repos' + chr(10) + ', '.join(f'`{r}/`' for r in INVESTIGATION_REPOS) + chr(10) + 'Do NOT search outside these directories.' + chr(10) + chr(10) if INVESTIGATION_REPOS else ''}"
        f"{_build_agent_context()}"
        f"## Instructions\n"
        f"1. Analyze the bug description and any attached screenshots\n"
        f"2. Search the codebase for relevant code paths{' (only in: ' + ', '.join(INVESTIGATION_REPOS) + ')' if INVESTIGATION_REPOS else ''}\n"
        f"3. Identify the root cause\n"
        f"4. Implement the fix — write the actual code changes\n"
        f"5. Write tests for the fix\n"
        f"6. Create a branch, commit, and open a PR:\n"
        f"   - Branch name: `fix/cfit-{task_info['id']}`\n"
        f"   - If the repo has a `/commit` or `/openpr` or similar slash command skill, use it\n"
        f"   - Otherwise: `git checkout -b fix/cfit-{task_info['id']}`, commit your changes, push, and open a PR with `gh pr create`\n"
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


def _is_cursor_running() -> bool:
    """Check if Cursor IDE is currently running."""
    result = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to (name of processes) contains "Cursor"'],
        capture_output=True, text=True,
    )
    return "true" in result.stdout.strip().lower()


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

    if cursor_already_open:
        # Cursor is already running — just reuse the existing workspace
        print(">>> Cursor already open — reusing existing workspace")
    else:
        # Open Cursor with investigation repos as a multi-root workspace
        subprocess.run(["open", "-a", "Cursor", repo_dirs[0]])
        if len(repo_dirs) > 1:
            time.sleep(3)
            for extra in repo_dirs[1:]:
                subprocess.run([_CURSOR_CLI, "--add", extra])

    subprocess.run(["pbcopy"], input=prompt.encode(), check=True)

    # Activate Cursor, open agent panel, click "New Agent" button to create session
    subprocess.run(["osascript", "-e", '''
        -- Wait for Cursor to be running
        tell application "System Events"
            repeat 30 times
                if exists (process "Cursor") then exit repeat
                delay 1
            end repeat
        end tell

        -- Activate and wait for it to be frontmost
        tell application "Cursor" to activate
        delay 2

        tell application "System Events"
            tell process "Cursor"
                set frontmost to true
                repeat 10 times
                    if frontmost then exit repeat
                    delay 0.5
                end repeat
            end tell
        end tell
        delay 1

        -- Open/focus the agent side panel (Cmd+Shift+L)
        tell application "System Events"
            keystroke "l" using {command down, shift down}
        end tell
        delay 2

        -- Click the "New Agent" button in the sidebar
        -- Get window position and click relative to it
        tell application "System Events"
            tell process "Cursor"
                set winPos to position of window 1
                set winX to item 1 of winPos
                set winY to item 2 of winPos
                -- "New Agent" button is in the sidebar, roughly 117px from left, 103px from top
                click at {winX + 117, winY + 103}
            end tell
        end tell
        delay 3
    '''])

    # Re-copy prompt right before paste (clipboard may have been overwritten)
    subprocess.run(["pbcopy"], input=prompt.encode(), check=True)

    print(">>> Pasting prompt and submitting...")
    subprocess.run(["osascript", "-e", '''
        tell application "Cursor" to activate
        delay 1
        tell application "System Events"
            tell process "Cursor"
                set frontmost to true
            end tell
            delay 0.5
            keystroke "v" using command down
            delay 2
            key code 36
        end tell
    '''])

    print(f">>> Task: {task_info['title']}")
    print(f">>> Cursor Agent is now investigating the bug")
    print(f">>> Watching for summary at: {OUTPUT_DIR}/{task_info['id']}/summary.txt")

    # Poll for the findings file and post to Asana when ready
    _wait_and_post_findings(task_info["id"])


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

    # Post the summary as a comment
    comment = f"🤖 AI Agent Investigation Results\n\n{summary}"
    try:
        post_comment(task_id, comment)
        print(">>> Summary posted as comment")
    except Exception as e:
        print(f">>> Error posting comment: {e}")

    # Attach findings.md with full details
    if findings_path.exists():
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
