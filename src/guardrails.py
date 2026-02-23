"""Guardrails for input sanitization and output safety."""

import hashlib
import logging
import re

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename to prevent path traversal and control character attacks."""
    sanitized = name
    while "../" in sanitized or "..\\" in sanitized:
        sanitized = sanitized.replace("../", "").replace("..\\", "")
    sanitized = re.sub(r"^[A-Za-z]:\\", "", sanitized)
    sanitized = sanitized.lstrip("/").lstrip("\\")
    sanitized = sanitized.replace("/", "").replace("\\", "")
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)
    sanitized = sanitized[:255]
    if not sanitized or sanitized.strip(".") == "":
        name_hash = hashlib.sha256(name.encode()).hexdigest()[:12]
        sanitized = f"attachment_{name_hash}"
    return sanitized


def sanitize_task_content(text: str) -> str:
    """Strip control characters from task content, preserving newlines and tabs."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def validate_task_id(task_id: str) -> bool:
    """Validate that a task ID is a reasonable Asana task identifier."""
    return bool(re.fullmatch(r"\d{5,25}", task_id))


_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token", re.compile(r"xox[bpas]-[0-9a-zA-Z-]+")),
    ("github_token", re.compile(r"gh[ps]_[a-zA-Z0-9]{36,}")),
    ("github_pat", re.compile(r"github_pat_[a-zA-Z0-9_]{20,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+")),
    ("connection_string", re.compile(r"(?:mongodb|postgres|mysql|redis)://[^\s]+")),
    ("generic_key", re.compile(r"(?:api[_-]?key|api[_-]?secret|access[_-]?key)\s*[=:]\s*['\"]?[a-zA-Z0-9_-]{20,}", re.IGNORECASE)),
    ("generic_token", re.compile(r"(?:token|bearer)\s*[=:]\s*['\"]?[a-zA-Z0-9_.-]{20,}", re.IGNORECASE)),
    ("generic_secret", re.compile(r"(?:secret|password|passwd)\s*[=:]\s*['\"]?[^\s'\"]{8,}", re.IGNORECASE)),
]


def scan_for_secrets(text: str) -> list[dict]:
    """Scan text for common secret patterns. Returns list of findings."""
    findings: list[dict] = []
    for secret_type, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append({
                "type": secret_type,
                "match": match.group(),
                "position": match.start(),
            })
    return findings


def redact_secrets(text: str) -> str:
    """Replace detected secrets with [REDACTED]. Logs a warning if any found."""
    findings = scan_for_secrets(text)
    if not findings:
        return text
    # Build spans and merge overlapping ones
    spans = sorted(
        [(f["position"], f["position"] + len(f["match"])) for f in findings]
    )
    merged = [spans[0]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    # Replace from right to left so positions stay valid
    redacted = text
    for start, end in reversed(merged):
        redacted = redacted[:start] + "[REDACTED]" + redacted[end:]
    types = set(f["type"] for f in findings)
    logger.warning(
        "Redacted %d secret(s) of types: %s",
        len(findings),
        ", ".join(sorted(types)),
    )
    return redacted


_TRUNCATION_SUFFIX = "\n\n[TRUNCATED — exceeded size limit]"


def check_size_limit(text: str, max_bytes: int) -> str:
    """Truncate text if it exceeds max_bytes. Appends a truncation notice."""
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    truncated = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + _TRUNCATION_SUFFIX
