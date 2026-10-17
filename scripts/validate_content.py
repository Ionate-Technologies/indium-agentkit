#!/usr/bin/env python3
"""Validate indium-agentkit skills, subagents, local references, and secrets."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from install import INTERNAL_ITEMS
from validate_handoff import HANDOFF_LABELS, REQUIRED_HEADINGS, normalize


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

# Authoring rules for distributed content (skills/ and agents/). The standard
# they enforce is described in skills/author-agentkit-content/SKILL.md.
WRITE_TOOLS = frozenset({"edit", "write", "multiedit", "notebookedit"})
READ_ONLY_ENDING = "Read-only."
WRITE_SCOPED_ENDING = "Edits only assigned paths."
DESCRIPTION_MIN_LENGTH = 80
DESCRIPTION_MAX_LENGTH = 600
TRIGGER_CUE = re.compile(r"(?i)\buse (?:when|for|after|before|proactively)\b")
YAML_INDICATORS = frozenset("`[{&*!|>%@")
SKILL_MAX_LINES = 400
AGENT_MAX_LINES = 250
BUILT_IN_AGENTS = frozenset({"general-purpose"})
FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`\n]*`")
NAME = r"([a-z0-9]+(?:-[a-z0-9]+)*)"
KIND_REFERENCE = re.compile(r"`" + NAME + r"`\s+(skill|subagent|agent)s?\b")
ROUTE_REFERENCE = re.compile(
    r"(?i)\b(?:route|delegate|hand ?off|escalate)\s+(?:\w+\s+)?to\s+(?:the\s+)?`" + NAME + r"`"
)
HANDOFF_MARKER = re.compile(r"^\s*<!--\s*handoff:\s*([a-z0-9-]+)\s*-->\s*$")
HANDOFF_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
HANDOFF_LABEL = re.compile(r"^\*\*([^*]+):\*\*", re.MULTILINE)
ALLOW_DESTRUCTIVE_MARKER = "<!-- agentkit-lint: allow-destructive -->"
APPROVAL_COMMENT = re.compile(r"(?i)(?:#|--|//)\s*requires approval\b")
CHECK_TOOLS = "pnpm|npm|yarn|npx|pytest|cargo|go|ruff|eslint|mypy|tsc|make"
DESTRUCTIVE_PATTERNS = {
    "`git checkout -- <path>` discards uncommitted work": re.compile(r"\bgit\s+checkout\s+--\s"),
    "`git reset --hard` discards uncommitted work": re.compile(r"\bgit\s+reset\s+--hard\b"),
    "`git clean -f` deletes untracked files": re.compile(r"\bgit\s+clean\s+-\w*f"),
    "`rm -rf` on a variable, glob, home, or root": re.compile(
        r"\brm\s+-\w*(?:rf|fr)\w*\s+(?:--\s+)?[\"']?(?:\$|\*|/|~|\.{1,2}(?:[\s/\"']|$))"
    ),
    "database `migrate reset` destroys data": re.compile(r"\bmigrate\s+reset\b"),
    "`pkill -f` can kill unrelated processes": re.compile(r"\bpkill\s+-f\b"),
    "`kubectl rollout undo` changes a live environment": re.compile(r"\bkubectl\s+rollout\s+undo\b"),
    "force push rewrites shared history": re.compile(
        r"\bgit\s+push\b[^\n]*(?:--force\b|--force-with-lease\b|\s-f\b)"
    ),
    "`||` fallback between tools hides failures": re.compile(
        r"\b(?:" + CHECK_TOOLS + r")\b[^\n|]*\|\|\s*(?:" + CHECK_TOOLS + r"|python3?)\b"
    ),
}


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


def split_markdown(text: str) -> tuple[list[str], list[tuple[int, list[tuple[int, str]], str]]]:
    """Split Markdown into prose and fenced code blocks.

    Returns prose lines with fenced lines blanked, so list positions still match
    line numbers, and fenced blocks as (opening line number, [(line number,
    text)], previous non-empty prose line).
    """
    prose: list[str] = []
    blocks: list[tuple[int, list[tuple[int, str]], str]] = []
    fence = ""
    current: tuple[int, list[tuple[int, str]], str] | None = None
    previous = ""
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if current is None:
            match = FENCE_OPEN.match(line)
            if match:
                fence = match.group(1)
                current = (number, [], previous)
                prose.append("")
            else:
                prose.append(line)
                if stripped:
                    previous = stripped
        elif stripped.startswith(fence) and not stripped.strip(fence[0]):
            blocks.append(current)
            current = None
            previous = ""
            prose.append("")
        else:
            current[1].append((number, line))
            prose.append("")
    if current is not None:
        blocks.append(current)
    return prose, blocks


def validate_local_links(root: Path, path: Path) -> list[str]:
    errors: list[str] = []
    try:
        content = read_text(path)
    except UnicodeDecodeError:
        return ["file is not valid UTF-8"]

    if path.suffix.lower() == ".md":
        # Links shown inside code are examples, not navigation.
        prose, _ = split_markdown(content)
        content = INLINE_CODE.sub("", "\n".join(prose))
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


def raw_frontmatter_value(path: Path, key: str) -> str:
    lines = read_text(path).splitlines()
    for line in lines[1:]:
        if line == FRONTMATTER_DELIMITER:
            break
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def is_write_scoped(tools: str) -> bool:
    """Return True when a tools line grants file-editing tools."""
    declared = {tool.strip().casefold() for tool in tools.split(",") if tool.strip()}
    return bool(declared & WRITE_TOOLS)


def validate_description(path: Path, description: str) -> list[str]:
    errors: list[str] = []
    raw = raw_frontmatter_value(path, "description")
    length = len(description)
    if not DESCRIPTION_MIN_LENGTH <= length <= DESCRIPTION_MAX_LENGTH:
        errors.append(
            f"description must be {DESCRIPTION_MIN_LENGTH} to {DESCRIPTION_MAX_LENGTH} "
            f"characters (found {length})"
        )
    if not TRIGGER_CUE.search(description):
        errors.append(
            'description must say when to use it ("Use when ...", "Use for ...", "Use proactively ...")'
        )
    if "<" in description or ">" in description:
        errors.append("description must not contain < or >")
    if raw[:1] in {'"', "'"}:
        if len(raw) < 2 or raw[-1] != raw[0] or raw[0] in raw[1:-1]:
            errors.append("description quoting is unbalanced or contains its own quote character")
    elif raw[:1] in YAML_INDICATORS or ": " in raw or " #" in raw:
        errors.append("unquoted description contains YAML syntax; wrap it in double quotes")
    return errors


def validate_agent_role(description: str, tools: str) -> list[str]:
    if is_write_scoped(tools):
        if not description.endswith(WRITE_SCOPED_ENDING):
            return [f'agents with Edit or Write tools must end the description with "{WRITE_SCOPED_ENDING}"']
    elif not description.endswith(READ_ONLY_ENDING):
        return [f'read-only agents must end the description with "{READ_ONLY_ENDING}"']
    return []


def validate_references(text: str, skill_names: set[str], agent_names: set[str]) -> list[str]:
    """Check that prose references to skills and subagents resolve."""
    prose, _ = split_markdown(text)
    joined = "\n".join(prose)
    errors: list[str] = []
    seen: set[tuple[int, str]] = set()

    def report(position: int, message: str) -> None:
        line = joined.count("\n", 0, position) + 1
        if (line, message) not in seen:
            seen.add((line, message))
            errors.append(f"line {line}: {message}")

    for match in KIND_REFERENCE.finditer(joined):
        name, kind = match.groups()
        known = skill_names if kind == "skill" else agent_names | BUILT_IN_AGENTS
        if name not in known:
            report(match.start(), f"reference to unknown {kind} `{name}`")
        elif name in INTERNAL_ITEMS:
            report(match.start(), f"distributed content must not refer to internal item `{name}`")
    for match in ROUTE_REFERENCE.finditer(joined):
        name = match.group(1)
        if name not in skill_names | agent_names | BUILT_IN_AGENTS:
            report(match.start(), f"route to unknown skill or subagent `{name}`")
        elif name in INTERNAL_ITEMS:
            report(match.start(), f"distributed content must not refer to internal item `{name}`")
    return errors


def validate_script_references(text: str, repo_scripts: set[str], skill_dir: Path | None) -> list[str]:
    """Reject references to files that consumers of the content do not receive."""
    errors: list[str] = []
    for name in sorted(repo_scripts):
        if re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", text):
            errors.append(f"references repository script `{name}`, which consumers do not receive")
    if "templates/handoffs/" in text:
        errors.append("references templates/handoffs/, which consumers do not receive; inline the headings")
    if skill_dir is not None and (skill_dir / "scripts").is_dir():
        for reference in sorted(set(re.findall(r"\bscripts/([\w./-]+\w)", text))):
            if not (skill_dir / "scripts" / reference).exists():
                errors.append(f"bundled script is missing: scripts/{reference}")
    return errors


def validate_destructive_commands(text: str) -> list[str]:
    """Reject destructive commands in code blocks unless they are approval-gated."""
    _, blocks = split_markdown(text)
    errors: list[str] = []
    for _, lines, previous in blocks:
        if previous == ALLOW_DESTRUCTIVE_MARKER:
            continue
        for number, line in lines:
            if APPROVAL_COMMENT.search(line):
                continue
            for label, pattern in DESTRUCTIVE_PATTERNS.items():
                if pattern.search(line):
                    errors.append(
                        f"line {number}: {label}; remove it or gate it behind an approval "
                        "step with a same-line '# requires approval' comment"
                    )
    return errors


def validate_handoffs(text: str) -> list[str]:
    """Check that inlined handoff blocks carry the headings validate_handoff requires."""
    errors: list[str] = []
    prose, blocks = split_markdown(text)
    lines = text.splitlines()
    for marker_line, line in enumerate(prose, start=1):
        marker = HANDOFF_MARKER.match(line)
        if marker is None:
            continue
        kind = marker.group(1)
        if kind not in REQUIRED_HEADINGS:
            errors.append(f"line {marker_line}: unknown handoff kind `{kind}`")
            continue
        block = next((item for item in blocks if item[0] > marker_line), None)
        between = lines[marker_line : block[0] - 1] if block else []
        if block is None or any(line.strip() for line in between):
            errors.append(f"line {marker_line}: handoff marker must be followed by a fenced block")
            continue
        body = "\n".join(line for _, line in block[1])
        headings = {normalize(value) for value in HANDOFF_HEADING.findall(body)}
        labels = {normalize(value) for value in HANDOFF_LABEL.findall(body)}
        for heading in sorted(REQUIRED_HEADINGS[kind] - headings):
            errors.append(f"line {marker_line}: {kind} handoff is missing heading: {heading}")
        for label in sorted(HANDOFF_LABELS - labels):
            errors.append(f"line {marker_line}: {kind} handoff is missing field: {label}")
    return errors


def validate_authoring(root: Path, skill_names: set[str], agent_names: set[str]) -> list[tuple[Path, str]]:
    """Apply the authoring standard to content distributed to consumer projects."""
    failures: list[tuple[Path, str]] = []
    scripts_dir = root / "scripts"
    repo_scripts = (
        {path.name for path in scripts_dir.iterdir() if path.is_file() and not path.name.startswith(".")}
        if scripts_dir.is_dir()
        else set()
    )

    for skill_dir in sorted(path for path in (root / "skills").iterdir() if path.is_dir()):
        internal = skill_dir.name in INTERNAL_ITEMS
        for document in sorted(skill_dir.rglob("*.md")):
            text = read_text(document)
            if document.name == "SKILL.md":
                fields, _ = parse_frontmatter(document)
                for error in validate_description(document, fields.get("description", "")):
                    failures.append((document, error))
                if len(text.splitlines()) > SKILL_MAX_LINES:
                    failures.append((document, f"SKILL.md exceeds {SKILL_MAX_LINES} lines"))
                for error in validate_handoffs(text):
                    failures.append((document, error))
            if not internal:
                for error in validate_references(text, skill_names, agent_names):
                    failures.append((document, error))
                for error in validate_script_references(text, repo_scripts, skill_dir):
                    failures.append((document, error))
            for error in validate_destructive_commands(text):
                failures.append((document, error))

    for agent_file in sorted((root / "agents").glob("*.md")):
        text = read_text(agent_file)
        fields, _ = parse_frontmatter(agent_file)
        description = fields.get("description", "")
        for error in validate_description(agent_file, description):
            failures.append((agent_file, error))
        for error in validate_agent_role(description, fields.get("tools", "")):
            failures.append((agent_file, error))
        if len(text.splitlines()) > AGENT_MAX_LINES:
            failures.append((agent_file, f"subagent file exceeds {AGENT_MAX_LINES} lines"))
        if agent_file.stem not in INTERNAL_ITEMS:
            for error in validate_references(text, skill_names, agent_names):
                failures.append((agent_file, error))
            for error in validate_script_references(text, repo_scripts, None):
                failures.append((agent_file, error))
        for error in validate_destructive_commands(text):
            failures.append((agent_file, error))

    consumer_template = root / "templates" / "AGENTS.md"
    if consumer_template.is_file():
        text = read_text(consumer_template)
        for error in validate_script_references(text, repo_scripts, None):
            failures.append((consumer_template, error))
        for error in validate_destructive_commands(text):
            failures.append((consumer_template, error))
    return failures


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
    skill_names: set[str] = set()
    agent_names: set[str] = set()
    if skills_dir.is_dir():
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

    # Authoring rules need well-formed frontmatter, so they run only after the
    # structural checks above pass.
    if skills_dir.is_dir() and agents_dir.is_dir() and not failures:
        failures.extend(validate_authoring(root, skill_names, agent_names))

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
