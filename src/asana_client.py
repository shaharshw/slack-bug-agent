import os
from pathlib import Path

import requests

from src.config import ASANA_ACCESS_TOKEN, OUTPUT_DIR

_BASE_URL = "https://app.asana.com/api/1.0"
_HEADERS = {"Authorization": f"Bearer {ASANA_ACCESS_TOKEN}"}


def fetch_task(task_id: str) -> dict:
    """Fetch task details from Asana and return a structured dict."""
    url = f"{_BASE_URL}/tasks/{task_id}"
    params = {
        "opt_fields": "name,notes,html_notes,custom_fields,due_on,assignee.email,assignee.name,tags.name,permalink_url",
    }
    resp = requests.get(url, headers=_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]

    assignee = data.get("assignee") or {}
    return {
        "id": task_id,
        "title": data.get("name", ""),
        "description": data.get("notes", ""),
        "html_description": data.get("html_notes", ""),
        "due_date": data.get("due_on"),
        "assignee_name": assignee.get("name"),
        "assignee_email": assignee.get("email"),
        "tags": [t["name"] for t in (data.get("tags") or [])],
        "custom_fields": {
            cf["name"]: cf.get("display_value")
            for cf in (data.get("custom_fields") or [])
        },
        "url": data.get("permalink_url", f"https://app.asana.com/0/0/{task_id}"),
    }


def fetch_attachments(task_id: str) -> list[str]:
    """Download all attachments for a task and return local file paths."""
    url = f"{_BASE_URL}/tasks/{task_id}/attachments"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    attachments = resp.json()["data"]

    if not attachments:
        return []

    task_dir = Path(OUTPUT_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    local_paths: list[str] = []
    for att in attachments:
        att_detail = _fetch_attachment_detail(att["gid"])
        if not att_detail:
            continue

        download_url = att_detail.get("download_url") or att_detail.get("permanent_url")
        if not download_url:
            continue

        filename = att_detail.get("name", att["gid"])
        local_path = task_dir / filename

        _download_file(download_url, local_path)
        local_paths.append(str(local_path))

    return local_paths


def _fetch_attachment_detail(attachment_id: str) -> dict | None:
    url = f"{_BASE_URL}/attachments/{attachment_id}"
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()["data"]


def post_comment(task_id: str, text: str) -> None:
    """Post a comment (story) on an Asana task."""
    url = f"{_BASE_URL}/tasks/{task_id}/stories"
    payload = {"data": {"text": text}}
    resp = requests.post(url, headers=_HEADERS, json=payload, timeout=30)
    resp.raise_for_status()


def upload_attachment(task_id: str, file_path: str) -> None:
    """Upload a file as an attachment to an Asana task."""
    url = f"{_BASE_URL}/tasks/{task_id}/attachments"
    # Asana attachment upload uses multipart form, not JSON — so no Content-Type in headers
    headers = {"Authorization": f"Bearer {ASANA_ACCESS_TOKEN}"}
    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            headers=headers,
            files={"file": (Path(file_path).name, f, "application/octet-stream")},
            timeout=60,
        )
    resp.raise_for_status()


def _download_file(url: str, dest: Path) -> None:
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
