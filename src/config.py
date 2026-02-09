import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

# Slack
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# Asana
ASANA_ACCESS_TOKEN = os.environ.get("ASANA_ACCESS_TOKEN", "")

# Slack channel to monitor (without leading #)
SLACK_CHANNEL_NAME = os.environ.get("SLACK_CHANNEL_NAME", "workforce-planning-core-bugs")

# Path to the repository the AI agent investigates
TARGET_REPO_PATH = os.path.expanduser(
    os.environ.get("TARGET_REPO_PATH", "~/workspace/core-objects")
)

# AI agent mode: "claude" or "cursor"
AGENT_MODE = os.environ.get("AGENT_MODE", "claude")

# Specific repos to investigate (comma-separated folder names under TARGET_REPO_PATH)
# e.g. "hibob,workforce-planning" — if empty, the agent searches the entire TARGET_REPO_PATH
_raw_repos = os.environ.get("INVESTIGATION_REPOS", "")
INVESTIGATION_REPOS = [r.strip() for r in _raw_repos.split(",") if r.strip()]

# Agent context files — repo rules/configs injected into the AI prompt
_raw_context_files = os.environ.get("AGENT_CONTEXT_FILES", "")
AGENT_CONTEXT_FILES = [f.strip() for f in _raw_context_files.split(",") if f.strip()]

# Directory for downloaded attachments and reports
OUTPUT_DIR = _project_root / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Asana URL pattern — used to extract task IDs from messages
# Handles both old (/0/project/task) and new (/1/workspace/task/id, /1/workspace/project/id/task/id) formats
ASANA_URL_PATTERN = r"https://app\.asana\.com/(?:0/\d+|(?:\d+/\d+/(?:project/\d+/)?task))/(\d+)"
