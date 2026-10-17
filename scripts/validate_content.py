#!/usr/bin/env python3
"""Validate indium-agentkit skills, subagents, local references, and secrets."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SKILL_FIELDS = {"name", "description"}
AGENT_FIELDS = {"name", "description", "tools", "model"}
FRONTMATTER_DELIMITER = "---"
KEY_VALUE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.+?)[ \t]*$")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
TEXT_SUFFIXES = {".md", ".py", ".sh", ".ps1", ".yml", ".yaml"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    try:
        lines = read_text(path).splitlines()
    except UnicodeDecodeError:
        return {}, ["file is not valid UTF-8"]

    if not lines or lines[0] != FRONTMATTER_DELIMITER:
        return {}, ["missing opening YAML frontmatter delimiter"]

    try:
        close_index = lines.index(FRONTMATTER_DELIMITER, 1)
    except ValueError:
        return {}, ["missing closing YAML frontmatter delimiter"]

    fields: dict[str, str] = {}
    errors: list[str] = []
    for line in lines[1:close_index]:
        match = KEY_VALUE.match(line)
        if not match:
            errors.append(f"unsupported frontmatter line: {line!r}")
            continue
        key, value = match.groups()
        if key in fields:
            errors.append(f"duplicate frontmatter field: {key}")
        fields[key] = value.strip().strip('"').strip("'")

    return fields, errors


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    fields, parse_errors = parse_frontmatter(skill_file)
    errors.extend(parse_errors)
    if set(fields) != SKILL_FIELDS:
        errors.append("frontmatter must contain only name and description")
    if fields.get("name") != skill_dir.name:
        errors.append("frontmatter name must match the skill directory name")
    if not fields.get("description", "").strip():
        errors.append("description must not be empty")
    return errors


def validate_agent(agent_file: Path) -> list[str]:
    fields, errors = parse_frontmatter(agent_file)
    if set(fields) != AGENT_FIELDS:
        errors.append("frontmatter must contain name, description, tools, and model")
    if fields.get("name") != agent_file.stem:
        errors.append("frontmatter name must match the agent filename")
    for field in ("description", "tools", "model"):
        if not fields.get(field, "").strip():
            errors.append(f"{field} must not be empty")
    return errors


def is_external_reference(target: str) -> bool:
    return target.startswith(("#", "http://", "https://", "mailto:", "tel:"))


def validate_local_links(root: Path, path: Path) -> list[str]:
    errors: list[str] = []
    try:
        content = read_text(path)
    except UnicodeDecodeError:
        return ["file is not valid UTF-8"]

    for raw_target in MARKDOWN_LINK.findall(content):
        target = raw_target.split("#", 1)[0].strip().strip("<>")
        if not target or is_external_reference(target):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"local link escapes repository: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"broken local link: {raw_target}")
    return errors


def validate_secrets(path: Path) -> list[str]:
    try:
        content = read_text(path)
    except UnicodeDecodeError:
        return ["file is not valid UTF-8"]
    return [f"possible {label}" for label, pattern in SECRET_PATTERNS.items() if pattern.search(content)]


def validate_repository(root: Path) -> list[tuple[Path, str]]:
    failures: list[tuple[Path, str]] = []
    required = [
        "AGENTS.md", "templates/AGENTS.md", "skills", "agents",
        "scripts/build_cursor_rules.py", "scripts/install.py",
        "scripts/install.sh", "scripts/install.ps1", "scripts/check_install.py",
        "scripts/scaffold_content.py", "scripts/list_content.py",
        "scripts/codex_delegate.py", "codex/README.md",
        "scripts/validate_handoff.py",
        "templates/subagent.md", "templates/skill.md",
        "scripts/generate_catalog.py", "scripts/diff_catalog.py",
        "scripts/sync_vendor_rules.py", "scripts/export_context_bundle.py",
        "scripts/verify_skill_overlap.py", "scripts/validate_rbac_schema.py",
        "templates/handoffs/feature-brief.md",
        "templates/handoffs/api-contract.md",
        "templates/handoffs/data-migration-plan.md",
        "templates/handoffs/verification-report.md",
        "templates/handoffs/onboarding-guide.md",
        "templates/handoffs/dependency-audit-report.md",
        "templates/handoffs/accessibility-audit-report.md",
        "templates/handoffs/llm-eval-report.md",
        "templates/handoffs/threat-model.md",
        "docs/compatibility.md", "docs/security.md", "docs/releasing.md",
        "CATALOG.md", "CHANGELOG.md", "SECURITY.md",
    ]
    for relative_path in required:
        if not (root / relative_path).exists():
            failures.append((root / relative_path, "required path is missing"))

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        skill_names: set[str] = set()
        for entry in sorted(skills_dir.iterdir()):
            if entry.name == ".gitkeep":
                continue
            if not entry.is_dir():
                failures.append((entry, "skill entries must be directories"))
                continue
            if entry.name in skill_names:
                failures.append((entry, "duplicate skill name"))
            skill_names.add(entry.name)
            for error in validate_skill(entry):
                failures.append((entry / "SKILL.md", error))

    agents_dir = root / "agents"
    if agents_dir.is_dir():
        agent_names: set[str] = set()
        for entry in sorted(agents_dir.iterdir()):
            if entry.name == ".gitkeep":
                continue
            if not entry.is_file() or entry.suffix != ".md":
                failures.append((entry, "subagents must be Markdown files"))
                continue
            if entry.stem in agent_names:
                failures.append((entry, "duplicate subagent name"))
            agent_names.add(entry.stem)
            for error in validate_agent(entry):
                failures.append((entry, error))

    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts or any(part.startswith(".") for part in path.relative_to(root).parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.suffix.lower() == ".md":
            for error in validate_local_links(root, path):
                failures.append((path, error))
        for error in validate_secrets(path):
            failures.append((path, error))

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate indium-agentkit content.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root to validate",
    )
    args = parser.parse_args()
    root = args.repo_root.expanduser().resolve()
    failures = validate_repository(root)
    if failures:
        for path, message in failures:
            print(f"error: {path.relative_to(root)}: {message}", file=sys.stderr)
        return 1
    print("content validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
