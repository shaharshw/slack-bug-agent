# Slack Bug Agent

Monitors a Slack channel for Asana CFIT tickets, fetches ticket data and attachments, and launches an AI agent (Claude Code or Cursor) to investigate bugs and post findings back to Asana.

## Install

```bash
# Clone the repo
git clone <repo-url> ~/workspace/slack-bug-agent
cd ~/workspace/slack-bug-agent

# Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install as a package
pip install -e .
```

## Setup

Run the interactive setup wizard:

```bash
slack-bug-agent --setup
```

It will walk you through:
1. Asana Personal Access Token
2. Slack App + Bot tokens (can skip if not yet approved)
3. Slack channel to monitor
4. Repository path for the AI agent
5. Agent mode (Cursor or Claude Code)

All settings are saved to `.env`.

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

```
Asana bot posts CFIT in Slack
  -> Script detects message, extracts Asana URL
    -> Fetches task details + downloads attachments
      -> Opens Cursor/Claude with bug context, auto-submits prompt
        -> Polls for AI agent's findings
          -> Posts summary as Asana comment + attaches detailed findings.md
```

## Prerequisites

- **macOS** (Cursor automation uses AppleScript)
- **Cursor** or **Claude Code CLI** installed
- **Accessibility permissions** for your terminal app (System Settings > Privacy & Security > Accessibility) — required for Cursor mode
- **Python 3.11+**

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_APP_TOKEN` | Slack App-Level Token for Socket Mode (`xapp-...`) |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (`xoxb-...`) |
| `ASANA_ACCESS_TOKEN` | Asana Personal Access Token |
| `SLACK_CHANNEL_NAME` | Channel to monitor (default: `workforce-planning-core-bugs`) |
| `TARGET_REPO_PATH` | Path to the repo for the AI agent (default: `~/workspace`) |
| `AGENT_MODE` | `claude` or `cursor` (default: `cursor`) |

## Sharing with Other Teams

Each developer runs the tool locally on their machine:

1. Clone the repo and install: `pip install -e .`
2. Run the setup wizard: `slack-bug-agent --setup`
3. Configure their team's channel and repo path
4. Slack App + Bot tokens are shared (same app for all teams)
5. Each developer needs their own Asana Personal Access Token
