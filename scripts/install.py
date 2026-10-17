#!/usr/bin/env python3
"""Install agentkit content into an explicit user or project scope."""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TARGETS = ("claude", "codex", "gemini", "antigravity", "cursor", "opencode")
SKILL_DESTINATIONS = {
    "claude": Path(".claude/skills"),
    "codex": Path(".codex/skills"),
    "gemini": Path(".gemini/skills"),
    "antigravity": Path(".antigravity/skills"),
    "opencode": Path(".opencode/skills"),
}
AGENT_DESTINATIONS = {
    "claude": Path(".claude/agents"),
    "gemini": Path(".gemini/agents"),
    "antigravity": Path(".antigravity/agents"),
}
# Content that only applies to this repository. It is left out of the default
# bundle but can still be installed explicitly with `add <name>`.
INTERNAL_ITEMS = frozenset({"author-agentkit-content"})


def paths_match(left: Path, right: Path) -> bool:
    if left.is_file() and right.is_file():
        return filecmp.cmp(left, right, shallow=False)
    if left.is_dir() and right.is_dir():
        comparison = filecmp.dircmp(left, right)
        return not (
            comparison.left_only
            or comparison.right_only
            or comparison.funny_files
            or comparison.diff_files
        ) and all(
            paths_match(left / name, right / name)
            for name in comparison.common_dirs
        )
    return False


def remove_link(path: Path) -> None:
    if path.is_dir() and os.name == "nt":
        path.rmdir()
    else:
        path.unlink()


def remove_existing(path: Path) -> None:
    if path.is_symlink():
        remove_link(path)
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def install_path(source: Path, destination: Path, mode: str, force: bool = False) -> str:
    """Install one artifact. With force, replace an existing destination of the same name."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.is_symlink():
        try:
            same_target = destination.resolve() == source.resolve()
        except OSError:
            same_target = False
        if mode == "link" and same_target:
            return f"unchanged: {destination} -> {source}"
        if mode == "copy" and not same_target and not force:
            return f"skipped:   {destination} is a symlink to another location"
        remove_link(destination)
        action = "migrated" if mode == "copy" else "updated"
    elif destination.exists():
        if mode == "copy" and paths_match(source, destination):
            return f"unchanged: {destination}"
        if not force:
            return (
                f"skipped:   {destination} exists and is not managed by this install "
                "(rerun with --force to replace it)"
            )
        remove_existing(destination)
        action = "replaced"
    else:
        action = "linked" if mode == "link" else "copied"

    if mode == "link":
        try:
            destination.symlink_to(source, target_is_directory=source.is_dir())
        except OSError as error:
            message = (
                f"Failed to create symbolic link '{destination}' -> '{source}'. "
                "On Windows, enable Developer Mode or run as Administrator. "
                f"Original error: {error}"
            )
            raise RuntimeError(message) from error
    elif source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return f"{action + ':':<11}{destination} -> {source}"


def select_content(repo_root: Path, item: str) -> tuple[list[Path], list[Path]]:
    skills_dir = repo_root / "skills"
    agents_dir = repo_root / "agents"
    skills = sorted(
        path for path in skills_dir.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
    )
    agents = sorted(agents_dir.glob("*.md"))
    if item == "all":
        return (
            [path for path in skills if path.name not in INTERNAL_ITEMS],
            [path for path in agents if path.stem not in INTERNAL_ITEMS],
        )

    selected_skills = [path for path in skills if path.name == item]
    selected_agents = [path for path in agents if path.stem == item]
    if not selected_skills and not selected_agents:
        raise ValueError(f"unknown skill or subagent: {item}")
    return selected_skills, selected_agents


def expand_targets(requested: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in requested:
        for target in value.split(","):
            normalized = target.strip().casefold()
            if normalized == "all":
                expanded.extend(TARGETS)
            elif normalized in TARGETS:
                expanded.append(normalized)
            else:
                raise ValueError(
                    f"unsupported target '{target}'; choose from {', '.join(TARGETS)} or all"
                )
    return list(dict.fromkeys(expanded))


def build_cursor_rules(
    repo_root: Path, destination: Path, skills: list[Path], item: str, force: bool = False
) -> None:
    if not skills:
        return
    with tempfile.TemporaryDirectory(prefix="indium-agentkit-cursor-") as temporary:
        generated_dir = Path(temporary)
        command = [
            sys.executable,
            str(repo_root / "scripts" / "build_cursor_rules.py"),
            "--skills-dir",
            str(repo_root / "skills"),
            "--out-dir",
            str(generated_dir),
        ]
        if item != "all":
            command.extend(("--skill", item))
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"Cursor rule generation failed with exit code {result.returncode}: {detail}"
            )
        for skill in skills:
            generated_rule = generated_dir / f"{skill.name}.mdc"
            print(install_path(generated_rule, destination / generated_rule.name, "copy", force))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install agentkit content into an explicit scope and target."
    )
    parser.add_argument("--scope", choices=("project", "user"), default="user")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Target agent; repeat or use a comma-separated list. Defaults to all.",
    )
    parser.add_argument("--item", default="all", help="One skill/subagent name or all")
    parser.add_argument("--mode", choices=("link", "copy"), default="link")
    parser.add_argument("--include-context", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing skills, subagents, and Cursor rules that have the same "
        "name as agentkit content (for example copies from an older version). "
        "Project context files are never replaced.",
    )
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.scope == "project":
        if args.project_dir is None:
            print("error: --project-dir is required for project scope", file=sys.stderr)
            return 2
        install_root = args.project_dir.expanduser().resolve()
        if not install_root.is_dir():
            print(f"error: project directory does not exist: {install_root}", file=sys.stderr)
            return 2
    else:
        if args.project_dir is not None:
            print("error: --project-dir cannot be used with user scope", file=sys.stderr)
            return 2
        install_root = args.home.expanduser().resolve()

    try:
        targets = expand_targets(args.target or ["all"])
        skills, agents = select_content(repo_root, args.item)
        compatible = any(
            (skills and (target in SKILL_DESTINATIONS or target == "cursor"))
            or (agents and target in AGENT_DESTINATIONS)
            for target in targets
        )
        if not compatible:
            raise ValueError(
                f"{args.item} has no native installation path for target(s): "
                f"{', '.join(targets)}"
            )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        for target in targets:
            skill_destination = SKILL_DESTINATIONS.get(target)
            if skill_destination:
                for skill in skills:
                    print(
                        install_path(
                            skill,
                            install_root / skill_destination / skill.name,
                            args.mode,
                            args.force,
                        )
                    )

            agent_destination = AGENT_DESTINATIONS.get(target)
            if agent_destination:
                for agent in agents:
                    print(
                        install_path(
                            agent,
                            install_root / agent_destination / agent.name,
                            args.mode,
                            args.force,
                        )
                    )

            if target == "cursor":
                build_cursor_rules(
                    repo_root, install_root / ".cursor" / "rules", skills, args.item, args.force
                )

        if args.scope == "project" and args.include_context:
            template = repo_root / "templates" / "AGENTS.md"
            if "claude" in targets:
                print(install_path(template, install_root / "CLAUDE.md", args.mode))
            if any(target != "claude" for target in targets):
                print(install_path(template, install_root / "AGENTS.md", args.mode))
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
