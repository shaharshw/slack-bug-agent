# Guardrails Design

## Goal

Add input sanitization and output safety guardrails to the slack-bug-agent, implemented as a single `src/guardrails.py` module.

## Input Sanitization

### Filename Sanitization (`sanitize_filename`)

Prevents path traversal and malicious filenames from Asana attachments.

- Strip `../`, `..\\`, leading `/` or drive letters (`C:\`)
- Remove null bytes (`\x00`) and control characters
- Limit to 255 characters
- If result is empty or only dots, fallback to `attachment_{hash_of_original}`

**Integration:** `asana_client.py:fetch_attachments` — sanitize before writing to disk.

### Task Content Sanitization (`sanitize_task_content`)

Strips dangerous characters from Asana task descriptions/titles before prompt injection.

- Remove control characters (preserve `\n`, `\t`, `\r`)
- No content rewriting — prompt injection defense is structural (XML delimiters in prompt)

**Integration:** `agent_launcher.py:build_prompt` — sanitize description and title, wrap user content in `<user-provided-content>` delimiters.

### Task ID Validation (`validate_task_id`)

- Must be purely numeric
- Length between 5 and 25 digits
- Returns `bool`

**Integration:** `slack_listener.py:_extract_task_id` — validate before processing.

## Output Safety

### Secret Scanning (`scan_for_secrets`)

Returns `list[dict]` with `{"type", "match", "position"}` for each finding.

Patterns detected:
- AWS access keys: `AKIA[0-9A-Z]{16}`
- Slack tokens: `xox[bpas]-[0-9a-zA-Z-]+`
- GitHub tokens: `gh[ps]_[a-zA-Z0-9]{36,}`, `github_pat_[a-zA-Z0-9_]{20,}`
- Private keys: `-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----`
- JWTs: `eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+`
- Generic key/token/secret/password assignments
- Connection strings: `mongodb://`, `postgres://`, `mysql://`, `redis://`

### Secret Redaction (`redact_secrets`)

- Calls `scan_for_secrets` internally
- Replaces each match with `[REDACTED]`
- Logs a warning with count and types of redacted secrets
- Returns the redacted text

**Integration:** `agent_launcher.py:_post_to_asana` — redact before posting comment and before uploading findings.

### Size Limits (`check_size_limit`)

- `summary.txt`: max 10KB
- `findings.md`: max 500KB
- If exceeded, truncate and append `\n\n[TRUNCATED — exceeded size limit]`
- Returns truncated text

**Integration:** `agent_launcher.py:_post_to_asana` — enforce before posting.

## File Structure

```
src/guardrails.py          # All guardrail functions
tests/test_guardrails.py   # Unit tests
```

## Integration Summary

| Caller | Function | When |
|--------|----------|------|
| `asana_client.fetch_attachments` | `sanitize_filename` | Before writing attachment to disk |
| `agent_launcher.build_prompt` | `sanitize_task_content` | Before injecting task content into prompt |
| `agent_launcher.build_prompt` | Wrap in `<user-provided-content>` delimiters | Structural prompt injection defense |
| `slack_listener._extract_task_id` | `validate_task_id` | After extracting ID, before processing |
| `agent_launcher._post_to_asana` | `redact_secrets` | Before posting comment to Asana |
| `agent_launcher._post_to_asana` | `check_size_limit` | Before posting comment / uploading file |
