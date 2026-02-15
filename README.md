# Slack Bug Agent

Monitors a Slack channel for Asana CFIT tickets, fetches ticket data and attachments, and launches an AI agent (Claude Code or Cursor) to investigate bugs and post findings back to Asana.

## Install

```bash
git clone <repo-url> ~/workspace/slack-bug-agent
cd ~/workspace/slack-bug-agent
pip install -e .
```

Optionally use a virtual environment to isolate dependencies:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Setup

Run the interactive setup wizard:

```bash
slack-bug-agent --setup
```

The wizard walks you through 7 steps:

1. **Slack tokens** — shared across the team, get from your team lead (`xapp-` + `xoxb-`). Only prompted on first install.
2. **Asana Personal Access Token** — create yours at https://app.asana.com/0/developer-console
3. **Slack channel** — the channel where CFITs are posted (e.g. `workforce-planning-core-bugs`)
4. **Workspace path** — your local workspace folder (e.g. `~/workspace`)
5. **Investigation repos** — the wizard scans your workspace path, lists all repos it finds, and lets you pick which ones the AI agent should investigate (comma-separated names or numbers, or leave empty for all)
6. **Agent mode** — `claude` (Claude Code CLI) or `cursor` (Cursor IDE)
7. **Agent context** — the wizard auto-discovers existing AI configs inside your selected repos:
   - `.cursorrules`
   - `.cursor/rules/*.mdc`
   - `CLAUDE.md`
   - `.ai-context/**/*.md` (guidelines, workflows, skills, etc.)

   Files matching `script`, `skill`, `workflow`, or `pr` in their path are injected as **available skills** the agent can use. Everything else is injected as **repo guidelines** the agent must follow. You choose which configs to include (`all`, specific numbers, or skip).

All settings are saved to `.env`. Re-run `slack-bug-agent --setup` anytime to update.

For Slack app creation details, see [setup_slack_app.md](setup_slack_app.md).

## Usage

```bash
# Start the Slack listener (monitors channel for new CFITs)
slack-bug-agent

# Process a single Asana task directly
slack-bug-agent --task-url "https://app.asana.com/1/xxx/task/yyy"

# Use a specific agent and repo
slack-bug-agent --task-url "<url>" --agent cursor --repo ~/workspace

# Simulate a Slack message (for testing)
slack-bug-agent --simulate

# Manually post findings to Asana
slack-bug-agent --post-results <task-id>
```

## How It Works

The app uses **Slack Socket Mode** — your local process opens a WebSocket connection outbound to Slack. No public URL, no server, no ngrok needed.

**Two tokens, two jobs:**
- `xapp-` (App Token) — establishes the WebSocket connection so Slack can push events to your machine
- `xoxb-` (Bot Token) — used for API calls back to Slack (reactions, channel info, etc.)

**Flow:**

```
Asana bot posts CFIT in Slack
  → Agent detects the message, extracts the Asana task URL
    → Fetches task details + downloads attachments (logs, screenshots)
      → Opens Cursor/Claude with the bug context + repo guidelines + skills
        → AI agent investigates the code across your selected repos
          → Polls for the agent's findings
            → Posts a summary comment on the Asana task + attaches a detailed findings.md
```

In Cursor mode, investigation repos are opened as a **multi-root workspace** (first repo opens, then additional repos are added via `cursor --add`) so indexing stays fast and scoped.

## Prerequisites

- **macOS** (Cursor automation uses AppleScript)
- **Cursor** or **Claude Code CLI** installed
- **Accessibility permissions** for your terminal app (System Settings > Privacy & Security > Accessibility) — required for Cursor mode
- **Python 3.11+**

## Slack App Permissions

The bot token needs these OAuth scopes:

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read messages in public channels |
| `channels:read` | Resolve channel names to IDs |
| `reactions:read` | Read emoji reactions |
| `reactions:write` | Add/remove emoji reactions (eyes, check mark, x) |

The app token needs **Socket Mode** enabled (connections:write).

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_APP_TOKEN` | Slack App-Level Token for Socket Mode (`xapp-...`) |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (`xoxb-...`) |
| `ASANA_ACCESS_TOKEN` | Asana Personal Access Token |
| `SLACK_CHANNEL_NAME` | Channel to monitor (default: `workforce-planning-core-bugs`) |
| `TARGET_REPO_PATH` | Base workspace folder (default: `~/workspace`) |
| `INVESTIGATION_REPOS` | Comma-separated repo folder names under workspace path (empty = all) |
| `AGENT_MODE` | `claude` or `cursor` (default: `cursor`) |
| `AGENT_CONTEXT_FILES` | Comma-separated absolute paths to agent config files injected into the prompt |

## Sharing with Other Teams

Each developer runs the tool locally on their machine:

1. Clone the repo and install: `pip install -e .`
2. Run the setup wizard: `slack-bug-agent --setup`
3. Configure their team's channel, repos, and agent context
4. Slack App + Bot tokens are shared (same app for all teams)
5. Each developer needs their own Asana Personal Access Token
