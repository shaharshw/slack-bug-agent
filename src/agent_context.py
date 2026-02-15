"""Scans repos for existing agent configurations (.cursorrules, .cursor/rules/, CLAUDE.md)."""

import os
from pathlib import Path


def scan_repos(workspace_path: str, repos: list[str]) -> list[dict]:
    """Scan repos for agent config files and return a list of discovered configs."""
    workspace = Path(os.path.expanduser(workspace_path))
    configs = []

    search_dirs = [workspace / r for r in repos] if repos else [workspace]

    for repo_dir in search_dirs:
        if not repo_dir.is_dir():
            continue

        repo_name = repo_dir.name

        # .cursorrules
        cursorrules = repo_dir / ".cursorrules"
        if cursorrules.is_file():
            configs.append({
                "repo": repo_name,
                "type": "cursorrules",
                "path": str(cursorrules),
                "name": f"{repo_name}/.cursorrules",
            })

        # .cursor/rules/*.mdc
        cursor_rules_dir = repo_dir / ".cursor" / "rules"
        if cursor_rules_dir.is_dir():
            for rule_file in sorted(cursor_rules_dir.glob("*.mdc")):
                configs.append({
                    "repo": repo_name,
                    "type": "cursor_rule",
                    "path": str(rule_file),
                    "name": f"{repo_name}/.cursor/rules/{rule_file.name}",
                })

        # CLAUDE.md
        claude_md = repo_dir / "CLAUDE.md"
        if claude_md.is_file():
            configs.append({
                "repo": repo_name,
                "type": "claude_md",
                "path": str(claude_md),
                "name": f"{repo_name}/CLAUDE.md",
            })

        # .ai-context/ directory (recursive — agents, workflows, guidelines, etc.)
        ai_context_dir = repo_dir / ".ai-context"
        if ai_context_dir.is_dir():
            for ctx_file in sorted(ai_context_dir.rglob("*.md")):
                rel_path = ctx_file.relative_to(repo_dir)
                configs.append({
                    "repo": repo_name,
                    "type": "ai_context",
                    "path": str(ctx_file),
                    "name": f"{repo_name}/{rel_path}",
                })

    return configs


def load_config_content(config: dict) -> str:
    """Read the content of an agent config file, stripping frontmatter from .mdc files."""
    content = Path(config["path"]).read_text(errors="replace").strip()

    # Strip YAML frontmatter from .mdc files (between --- markers)
    if config["type"] == "cursor_rule" and content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    return content


def build_context_section(configs: list[dict]) -> str:
    """Build a prompt section that references agent configs by path instead of inlining them."""
    if not configs:
        return ""

    # Separate scripts/skills/workflows from guidelines
    scripts = []
    guidelines = []
    for config in configs:
        name_lower = config["name"].lower()
        if any(k in name_lower for k in ("script", "skill", "workflow", "open-pr", "pr.md")):
            scripts.append(config)
        else:
            guidelines.append(config)

    parts = []

    if scripts:
        file_list = "\n".join(f"- `{c['path']}`" for c in scripts)
        parts.append(
            "## Available Scripts & Skills\n"
            "The repos have these scripts/skills. Read them and USE THEM when applicable "
            "(e.g. for opening PRs, committing, running workflows).\n\n"
            f"{file_list}"
        )

    if guidelines:
        file_list = "\n".join(f"- `{c['path']}`" for c in guidelines)
        parts.append(
            "## Repo Guidelines & Rules\n"
            "Read these files before writing code — they contain coding conventions, "
            "patterns, and rules you must follow.\n\n"
            f"{file_list}"
        )

    if not parts:
        return ""

    return "\n\n".join(parts) + "\n\n"
