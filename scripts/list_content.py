#!/usr/bin/env python3
"""List indium-agentkit skills and subagents from frontmatter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from install import INTERNAL_ITEMS
from validate_content import parse_frontmatter


def collect(repo_root: Path) -> list[dict[str, str]]:
    content: list[dict[str, str]] = []
    for skill_file in sorted((repo_root / "skills").glob("*/SKILL.md")):
        fields, _ = parse_frontmatter(skill_file)
        name = fields.get("name", skill_file.parent.name)
        kind = "skill (internal)" if name in INTERNAL_ITEMS else "skill"
        content.append({"kind": kind, "name": name, "description": fields.get("description", "")})
    for agent_file in sorted((repo_root / "agents").glob("*.md")):
        fields, _ = parse_frontmatter(agent_file)
        name = fields.get("name", agent_file.stem)
        kind = "subagent (internal)" if name in INTERNAL_ITEMS else "subagent"
        content.append({"kind": kind, "name": name, "description": fields.get("description", "")})
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="List indium-agentkit content.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    content = collect(args.repo_root.resolve())
    if args.format == "json":
        print(json.dumps(content, indent=2))
        return 0
    print("| Kind | Name | Description |\n| --- | --- | --- |")
    for item in content:
        description = item["description"].replace("|", "\\|")
        print(f"| {item['kind']} | `{item['name']}` | {description} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
