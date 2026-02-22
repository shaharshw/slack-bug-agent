import json
import re
import threading

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.asana_client import fetch_attachments, fetch_task
from src.agent_launcher import launch
from src import config

app = None  # Initialized lazily in start_listener()

# Cache the target channel ID — resolved lazily from first matching message
_target_channel_id: str | None = None
_channel_resolved: bool = False


def _check_channel(event: dict) -> bool:
    """Check if a message is from the target channel.

    On first Asana bot message, resolve the channel name via conversations.info
    (single cheap API call) and cache the ID for future messages.
    """
    global _target_channel_id, _channel_resolved

    channel_id = event.get("channel")
    if not channel_id:
        return False

    # Already resolved — fast path
    if _channel_resolved:
        return channel_id == _target_channel_id

    # Not yet resolved — check this channel's name
    try:
        resp = app.client.conversations_info(channel=channel_id)
        ch_name = resp["channel"]["name"]
        if ch_name == config.SLACK_CHANNEL_NAME:
            _target_channel_id = channel_id
            _channel_resolved = True
            print(f"Resolved #{config.SLACK_CHANNEL_NAME} → {channel_id}")
            return True
    except Exception:
        pass

    return False


def _is_asana_bot_message(event: dict) -> bool:
    """Check if the message originates from the Asana Slack integration."""
    # Asana bot messages have bot_profile with name containing "Asana"
    bot_profile = event.get("bot_profile", {})
    if bot_profile and "asana" in (bot_profile.get("name") or "").lower():
        return True
    # Fallback: any message that contains an Asana URL
    return bool(re.search(config.ASANA_URL_PATTERN, event.get("text", "")))


def _extract_task_id(event: dict) -> str | None:
    """Extract the Asana task ID from a Slack event.

    The Asana bot stores the task ID in attachments[].callback_id as JSON:
    {"taskId": "123456", "workspaceId": "789"}
    Falls back to regex matching on text/URLs.
    """
    # Primary: callback_id in attachments
    for att in event.get("attachments", []):
        cb = att.get("callback_id", "")
        if cb:
            try:
                data = json.loads(cb)
                if "taskId" in data:
                    return data["taskId"]
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: title_link or action URLs
        for url_field in [att.get("title_link", "")] + [a.get("url", "") for a in att.get("actions", [])]:
            match = re.search(r"/(\d{10,})/", url_field)
            if match:
                return match.group(1)

    # Last resort: regex on text
    match = re.search(config.ASANA_URL_PATTERN, event.get("text", ""))
    if match:
        return match.group(1)

    return None


def _react(channel: str, ts: str, emoji: str) -> None:
    """Add a reaction emoji to a Slack message."""
    try:
        app.client.reactions_add(channel=channel, timestamp=ts, name=emoji)
    except Exception as e:
        print(f"  Failed to add :{emoji}: reaction: {e}")


def _unreact(channel: str, ts: str, emoji: str) -> None:
    """Remove a reaction emoji from a Slack message."""
    try:
        app.client.reactions_remove(channel=channel, timestamp=ts, name=emoji)
    except Exception as e:
        print(f"  Failed to remove :{emoji}: reaction: {e}")



def _process_task(task_id: str, channel: str, ts: str) -> None:
    """Fetch task, launch agent, and update reactions. Runs in a background thread."""
    try:
        task_info = fetch_task(task_id)
        print(f"Title: {task_info['title']}")

        attachment_paths = fetch_attachments(task_id)
        if attachment_paths:
            print(f"Downloaded {len(attachment_paths)} attachment(s)")

        launch(task_info, attachment_paths, config.TARGET_REPO_PATH, mode=config.AGENT_MODE)

        # Done — swap 👀 for ✅
        _unreact(channel, ts, "eyes")
        _react(channel, ts, "white_check_mark")
    except Exception as e:
        # Error — swap 👀 for ❌
        _unreact(channel, ts, "eyes")
        _react(channel, ts, "x")
        print(f"Error processing task {task_id}: {e}")


def handle_message(event: dict, say) -> None:
    subtype = event.get("subtype", "")
    channel_id = event.get("channel", "")

    if not _check_channel(event):
        return

    # Log all messages in the target channel for debugging
    print(f"  [debug] message in channel | subtype={subtype!r} bot={bool(event.get('bot_profile'))} text={event.get('text', '')[:80]!r}")

    if not _is_asana_bot_message(event):
        return

    # Extract task ID — Asana bot puts it in attachments[].callback_id
    task_id = _extract_task_id(event)
    if not task_id:
        print(f"  [debug] Asana bot message but could not extract task ID")
        return

    channel = event["channel"]
    ts = event["ts"]

    print(f"\n{'='*60}")
    print(f"New CFIT detected — Asana task {task_id}")
    print(f"{'='*60}")

    # React with 👀 to indicate the bot is investigating
    _react(channel, ts, "eyes")

    # Run in background thread so the Slack listener stays responsive
    thread = threading.Thread(
        target=_process_task,
        args=(task_id, channel, ts),
        daemon=True,
    )
    thread.start()


def start_listener() -> None:
    global app

    # The socket mode client logs BrokenPipeError / SSLError at ERROR level
    # during normal reconnection — suppress everything below CRITICAL.
    # The logger lives in .builtin.client (not .connection) since Connection
    # receives the client's logger instance.
    logging.getLogger("slack_sdk.socket_mode.builtin").setLevel(logging.CRITICAL)

    app = App(token=config.SLACK_BOT_TOKEN)
    app.event("message")(handle_message)

    print(f"Listening for Asana CFIT tickets in #{config.SLACK_CHANNEL_NAME}...")
    print(f"Agent mode: {config.AGENT_MODE}")
    print(f"Target repo: {config.TARGET_REPO_PATH}")
    handler = SocketModeHandler(app, config.SLACK_APP_TOKEN)
    handler.start()
