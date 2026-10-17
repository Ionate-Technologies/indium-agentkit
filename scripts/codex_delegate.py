#!/usr/bin/env python3
"""Build a structured delegation packet from an agentkit role prompt.

This adapter deliberately does not call a model. A Codex app, CLI wrapper, or
Responses API orchestrator can pass the emitted packet to its native delegation
mechanism while retaining explicit scope and output requirements.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validate_content import is_write_scoped, parse_frontmatter


def build_packet(repo_root: Path, agent_name: str, task: str, files: list[str]) -> dict[str, object]:
    agent_path = repo_root / "agents" / f"{agent_name}.md"
    if not agent_path.is_file():
        raise ValueError(f"unknown agent: {agent_name}")
    fields, errors = parse_frontmatter(agent_path)
    if errors:
        raise ValueError(f"invalid agent frontmatter: {'; '.join(errors)}")

    role_prompt = agent_path.read_text(encoding="utf-8")
    return {
        "agent": {
            "name": fields.get("name", agent_name),
            "description": fields.get("description", ""),
            "tools": fields.get("tools", ""),
            "model": fields.get("model", "inherit"),
        },
        "task": task,
        "allowed_files": files,
        "write_mode": "scoped" if is_write_scoped(fields.get("tools", "")) else "read-only",
        "output_requirements": [
            "evidence-backed findings",
            "exact files, lines, or commands where applicable",
            "assumptions and confidence",
            "unverified items and recommended next action",
        ],
        "prompt": (
            f"You are the {agent_name} specialist.\n\n"
            f"Role definition:\n{role_prompt}\n\n"
            f"Assigned task:\n{task}\n\n"
            f"Allowed files or scope:\n{chr(10).join(files) if files else '(none specified)'}\n\n"
            "Return only the required evidence-backed report. Do not expand scope."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Codex delegation packet.")
    parser.add_argument("--agent", required=True, help="Name matching agents/<name>.md")
    parser.add_argument("--task", required=True, help="Bounded task for the delegated run")
    parser.add_argument("--files", nargs="*", default=[], help="Allowed files or paths")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--format", choices=("json", "prompt"), default="json")
    args = parser.parse_args()

    try:
        packet = build_packet(args.repo_root.resolve(), args.agent, args.task, args.files)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.format == "prompt":
        print(packet["prompt"])
    else:
        print(json.dumps(packet, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
