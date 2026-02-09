"""Entry point for the Slack Bug Agent.

Usage:
    # Setup wizard (first-time configuration):
    slack-bug-agent --setup

    # Socket Mode listener (monitors Slack channel):
    slack-bug-agent

    # Manual mode (process a single Asana task URL):
    slack-bug-agent --task-url "https://app.asana.com/0/xxx/yyy"
    slack-bug-agent --task-url "https://app.asana.com/0/xxx/yyy" --agent cursor
"""

import argparse
import re
import sys

from src.config import AGENT_MODE, ASANA_URL_PATTERN, TARGET_REPO_PATH


def run_simulate(agent_mode: str, repo_path: str) -> None:
    """Simulate a Slack message from the Asana bot to test the full pipeline."""
    from src.slack_listener import handle_message

    fake_event = {
        "type": "message",
        "channel": "C_SIMULATED",
        "text": "New task created: <https://app.asana.com/1/103035621276259/task/1212983431153004|WFP - error when aligning positions>",
        "bot_profile": {"name": "Asana"},
    }

    print("Simulating Asana bot message in Slack...")
    print(f"Message: {fake_event['text']}")

    # Bypass channel filter for simulation
    from src import slack_listener
    slack_listener._target_channel_id = "C_SIMULATED"

    # Override agent mode and repo path
    from src import config
    config.AGENT_MODE = agent_mode
    config.TARGET_REPO_PATH = repo_path

    handle_message(fake_event, say=lambda *a, **kw: None)


def run_manual(task_url: str, agent_mode: str, repo_path: str) -> None:
    from src.asana_client import fetch_attachments, fetch_task
    from src.agent_launcher import launch

    match = re.search(ASANA_URL_PATTERN, task_url)
    if not match:
        print(f"Error: Could not extract Asana task ID from URL: {task_url}")
        sys.exit(1)

    task_id = match.group(1)
    print(f"Fetching Asana task {task_id}...")

    task_info = fetch_task(task_id)
    print(f"Title: {task_info['title']}")

    attachment_paths = fetch_attachments(task_id)
    if attachment_paths:
        print(f"Downloaded {len(attachment_paths)} attachment(s)")
    else:
        print("No attachments found")

    launch(task_info, attachment_paths, repo_path, mode=agent_mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Slack Bug Agent — CFIT automation")
    parser.add_argument(
        "--task-url",
        help="Asana task URL to process directly (skips Slack listener)",
    )
    parser.add_argument(
        "--agent",
        choices=["claude", "cursor"],
        default=AGENT_MODE,
        help=f"AI agent to use (default: {AGENT_MODE})",
    )
    parser.add_argument(
        "--repo",
        default=TARGET_REPO_PATH,
        help=f"Path to the repository (default: {TARGET_REPO_PATH})",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate a Slack message with an Asana link (tests full pipeline without Slack)",
    )
    parser.add_argument(
        "--post-results",
        metavar="TASK_ID",
        help="Manually post findings to Asana for a given task ID",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run the interactive setup wizard",
    )
    args = parser.parse_args()

    if args.setup:
        from src.setup_wizard import run_setup
        run_setup()
        return

    if args.post_results:
        from src.agent_launcher import post_results
        post_results(args.post_results)
    elif args.task_url:
        run_manual(args.task_url, args.agent, args.repo)
    elif args.simulate:
        run_simulate(args.agent, args.repo)
    else:
        from src.slack_listener import start_listener
        start_listener()


if __name__ == "__main__":
    main()
