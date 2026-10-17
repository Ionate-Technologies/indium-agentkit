#!/usr/bin/env python3
"""Export all skills, agents, and handoff templates into a single standalone Markdown bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from install import INTERNAL_ITEMS
from sync_vendor_rules import extract_body


def export_bundle(repo_root: Path) -> str:
    lines = [
        "# Indium Agentkit Consolidated Context Bundle",
        "",
        "Single-file bundle containing all portable skills, agents, and standards.",
        "Suitable for copy-pasting into Web LLMs or single-context prompt environments.",
        "",
        "---",
        "",
    ]
    for skill_file in sorted((repo_root / "skills").glob("*/SKILL.md")):
        fields, body = extract_body(skill_file)
        name = fields.get("name", skill_file.parent.name)
        if name in INTERNAL_ITEMS:
            continue
        desc = fields.get("description", "")
        lines.append(f"# [SKILL] {name}")
        lines.append(f"**Description**: {desc}")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    for agent_file in sorted((repo_root / "agents").glob("*.md")):
        fields, body = extract_body(agent_file)
        name = fields.get("name", agent_file.stem)
        if name in INTERNAL_ITEMS:
            continue
        desc = fields.get("description", "")
        lines.append(f"# [SUBAGENT] {name}")
        lines.append(f"**Description**: {desc}")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export all agentkit content into a single Markdown file.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: <repo-root>/dist/agentkit-bundle.md)",
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output or root / "dist" / "agentkit-bundle.md").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bundle_text = export_bundle(root)
    output.write_text(bundle_text, encoding="utf-8")
    print(f"exported bundle to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
