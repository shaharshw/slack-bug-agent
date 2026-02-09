"""Interactive setup wizard for Slack Bug Agent."""

import os
from pathlib import Path

import requests


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    """Prompt the user for input with an optional default."""
    if default:
        display = f"{label} [{default}]: "
    else:
        display = f"{label}: "

    value = input(display).strip()
    return value or default


def _validate_asana_token(token: str) -> bool:
    """Check if the Asana token works."""
    try:
        resp = requests.get(
            "https://app.asana.com/api/1.0/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            name = resp.json()["data"].get("name", "Unknown")
            print(f"  Asana: authenticated as {name}")
            return True
        print(f"  Asana: authentication failed (HTTP {resp.status_code})")
        return False
    except Exception as e:
        print(f"  Asana: connection error — {e}")
        return False


def _validate_slack_tokens(app_token: str, bot_token: str) -> bool:
    """Check if Slack tokens work."""
    ok = True

    if app_token:
        if not app_token.startswith("xapp-"):
            print("  Slack App Token: should start with 'xapp-'")
            ok = False
        else:
            print("  Slack App Token: format OK")
    else:
        print("  Slack App Token: skipped (can set up later)")

    if bot_token:
        try:
            from slack_sdk import WebClient
            client = WebClient(token=bot_token)
            resp = client.auth_test()
            print(f"  Slack Bot: authenticated as @{resp['user']}")
        except Exception as e:
            print(f"  Slack Bot: authentication failed — {e}")
            ok = False
    else:
        print("  Slack Bot Token: skipped (can set up later)")

    return ok


def _validate_repo_path(path: str) -> bool:
    """Check if the repo path exists."""
    expanded = os.path.expanduser(path)
    if os.path.isdir(expanded):
        print(f"  Repo path: found at {expanded}")
        return True
    print(f"  Repo path: directory not found — {expanded}")
    return False


def run_setup() -> None:
    """Run the interactive setup wizard."""
    print()
    print("=" * 50)
    print("  Slack Bug Agent — Setup Wizard")
    print("=" * 50)
    print()

    # Load existing values if .env exists
    existing = {}
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()
        print("Found existing .env — press Enter to keep current values.\n")

    # --- Asana ---
    print("--- Asana Token ---")
    print("Get yours at: https://app.asana.com/0/developer-console")
    print("Create a Personal Access Token and paste it below.\n")
    asana_token = _prompt(
        "Asana Access Token",
        default=existing.get("ASANA_ACCESS_TOKEN", ""),
    )
    print()

    # --- Slack ---
    print("--- Slack Tokens ---")
    print("Follow setup_slack_app.md to create your Slack app.")
    print("If not approved yet, leave these blank and add later.\n")
    slack_app_token = _prompt(
        "Slack App Token (xapp-...)",
        default=existing.get("SLACK_APP_TOKEN", ""),
    )
    slack_bot_token = _prompt(
        "Slack Bot Token (xoxb-...)",
        default=existing.get("SLACK_BOT_TOKEN", ""),
    )
    print()

    # --- Channel ---
    print("--- Slack Channel ---")
    channel = _prompt(
        "Channel to monitor (without #)",
        default=existing.get("SLACK_CHANNEL_NAME", "workforce-planning-core-bugs"),
    )
    print()

    # --- Repo ---
    print("--- Repository Path ---")
    print("The base workspace folder that Cursor/Claude will open.\n")
    repo_path = _prompt(
        "Workspace path",
        default=existing.get("TARGET_REPO_PATH", "~/workspace"),
    )
    print()

    # --- Investigation Repos ---
    print("--- Investigation Repos ---")
    expanded_repo = os.path.expanduser(repo_path)
    if os.path.isdir(expanded_repo):
        subdirs = sorted(
            d.name for d in Path(expanded_repo).iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if subdirs:
            print(f"Found repos under {repo_path}:")
            for i, d in enumerate(subdirs, 1):
                print(f"  {i}. {d}")
            print()
            print("Which repos should the AI agent investigate?")
            print("Enter comma-separated names or numbers (leave empty for all).\n")

    investigation_repos = _prompt(
        "Repos to investigate",
        default=existing.get("INVESTIGATION_REPOS", ""),
    )

    # Resolve numbers to names if the user entered numbers
    if investigation_repos and os.path.isdir(expanded_repo):
        resolved = []
        for part in investigation_repos.split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= len(subdirs):
                resolved.append(subdirs[int(part) - 1])
            else:
                resolved.append(part)
        investigation_repos = ",".join(resolved)

    if investigation_repos:
        print(f"  Will investigate: {investigation_repos}")
    else:
        print("  Will investigate entire workspace")
    print()

    # --- Agent Mode ---
    print("--- AI Agent ---")
    agent_mode = _prompt(
        "Agent mode (claude/cursor)",
        default=existing.get("AGENT_MODE", "cursor"),
    )
    if agent_mode not in ("claude", "cursor"):
        print(f"  Warning: unknown mode '{agent_mode}', defaulting to 'cursor'")
        agent_mode = "cursor"
    print()

    # --- Agent Context ---
    agent_context_files = ""
    repos_list = [r.strip() for r in investigation_repos.split(",") if r.strip()]
    if os.path.isdir(expanded_repo):
        from src.agent_context import scan_repos
        configs = scan_repos(repo_path, repos_list)
        if configs:
            print("--- Agent Context ---")
            print("Found existing agent rules/configs in your repos:\n")
            for i, cfg in enumerate(configs, 1):
                print(f"  {i}. {cfg['name']}")
            print()
            print("Which configs should be included in the AI agent's prompt?")
            print("Enter comma-separated numbers, 'all' for everything, or leave empty to skip.\n")
            selection = _prompt("Include configs", default=existing.get("AGENT_CONTEXT_FILES", "all"))

            if selection.lower() == "all":
                agent_context_files = ",".join(cfg["path"] for cfg in configs)
                print(f"  Including all {len(configs)} configs")
            elif selection:
                selected = []
                for part in selection.split(","):
                    part = part.strip()
                    if part.isdigit() and 1 <= int(part) <= len(configs):
                        selected.append(configs[int(part) - 1]["path"])
                agent_context_files = ",".join(selected)
                print(f"  Including {len(selected)} config(s)")
            else:
                print("  Skipping agent context")
            print()

    # --- Validate ---
    print("--- Validating ---")
    if asana_token:
        _validate_asana_token(asana_token)
    _validate_slack_tokens(slack_app_token, slack_bot_token)
    _validate_repo_path(repo_path)
    print()

    # --- Write .env ---
    env_content = f"""\
# Slack tokens
SLACK_APP_TOKEN={slack_app_token}
SLACK_BOT_TOKEN={slack_bot_token}

# Asana token
ASANA_ACCESS_TOKEN={asana_token}

# Channel to monitor (without #)
SLACK_CHANNEL_NAME={channel}

# Workspace path (Cursor/Claude opens this folder)
TARGET_REPO_PATH={repo_path}

# Repos to investigate (comma-separated folder names under TARGET_REPO_PATH)
# Leave empty to search the entire workspace
INVESTIGATION_REPOS={investigation_repos}

# AI agent mode: "claude" or "cursor"
AGENT_MODE={agent_mode}

# Agent context files (comma-separated absolute paths to .cursorrules, .mdc, CLAUDE.md)
# These are injected into the AI agent's prompt so it follows repo conventions
AGENT_CONTEXT_FILES={agent_context_files}
"""
    _ENV_PATH.write_text(env_content)
    print(f"Configuration saved to {_ENV_PATH}")
    print()

    # --- Next steps ---
    print("--- Next Steps ---")
    if not slack_bot_token:
        print("1. Once your Slack app is approved, run setup again to add the bot token")
        print("2. Invite the bot to the channel: /invite @bug-agent-bot")
    else:
        print("1. Invite the bot to the channel: /invite @bug-agent-bot")

    if agent_mode == "cursor":
        print(f"{'2' if slack_bot_token else '3'}. Grant Accessibility permissions: System Settings > Privacy & Security > Accessibility > enable Terminal")

    print()
    print("To start the listener:  slack-bug-agent")
    print("To process a task:      slack-bug-agent --task-url <asana-url>")
    print()
