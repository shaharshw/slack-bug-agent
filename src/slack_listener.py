import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.asana_client import fetch_attachments, fetch_task
from src.agent_launcher import launch
from src import config

app = None  # Initialized lazily in start_listener()

# Cache the target channel ID so we only process relevant messages
_target_channel_id: str | None = None


def _resolve_channel_id() -> str | None:
    """Look up channel ID by name (once)."""
    global _target_channel_id
    if _target_channel_id:
        return _target_channel_id

    cursor = None
    while True:
        resp = app.client.conversations_list(
            types="public_channel,private_channel",
            limit=200,
            cursor=cursor,
        )
        for ch in resp["channels"]:
            if ch["name"] == config.SLACK_CHANNEL_NAME:
                _target_channel_id = ch["id"]
                return _target_channel_id
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return None


def _is_asana_bot_message(event: dict) -> bool:
    """Check if the message originates from the Asana Slack integration."""
    # Asana bot messages have bot_profile with name containing "Asana"
    bot_profile = event.get("bot_profile", {})
    if bot_profile and "asana" in (bot_profile.get("name") or "").lower():
        return True
    # Fallback: any message that contains an Asana URL
    return bool(re.search(config.ASANA_URL_PATTERN, event.get("text", "")))


def handle_message(event: dict, say) -> None:
    channel_id = _resolve_channel_id()

    # Only process messages from the target channel
    if channel_id and event.get("channel") != channel_id:
        return

    if not _is_asana_bot_message(event):
        return

    text = event.get("text", "")
    # Also check attachments/blocks for Asana URLs
    for block in event.get("blocks", []):
        for element in block.get("elements", []):
            for item in element.get("elements", []):
                if item.get("type") == "link":
                    text += " " + item.get("url", "")

    match = re.search(config.ASANA_URL_PATTERN, text)
    if not match:
        return

    task_id = match.group(1)
    print(f"\n{'='*60}")
    print(f"New CFIT detected — Asana task {task_id}")
    print(f"{'='*60}")

    try:
        task_info = fetch_task(task_id)
        print(f"Title: {task_info['title']}")

        attachment_paths = fetch_attachments(task_id)
        if attachment_paths:
            print(f"Downloaded {len(attachment_paths)} attachment(s)")

        launch(task_info, attachment_paths, config.TARGET_REPO_PATH, mode=config.AGENT_MODE)
    except Exception as e:
        print(f"Error processing task {task_id}: {e}")


def start_listener() -> None:
    global app
    app = App(token=config.SLACK_BOT_TOKEN)
    app.event("message")(handle_message)

    print(f"Monitoring #{config.SLACK_CHANNEL_NAME} for Asana CFIT tickets...")
    print(f"Agent mode: {config.AGENT_MODE}")
    print(f"Target repo: {config.TARGET_REPO_PATH}")
    handler = SocketModeHandler(app, config.SLACK_APP_TOKEN)
    handler.start()
