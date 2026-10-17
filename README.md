# indium-agentkit

`indium-agentkit` distributes portable AI coding-agent skills, subagents, and
project context across Claude Code, Codex, Gemini CLI, Antigravity, OpenCode,
and Cursor.

## Quick start

Install the complete bundle into one agent inside the current project:

```bash
npx @indium-ai-labs/agentkit install --target=codex
```

Install one skill instead of the complete bundle:

```bash
npx @indium-ai-labs/agentkit add systematic-debugging --target=codex
```

Project scope is the default. These commands write only below the current
project; they do not modify user-level agent directories. Choose a different
project explicitly with `--project-dir`:

```bash
npx @indium-ai-labs/agentkit install \
  --project-dir=/path/to/project \
  --target=claude
```

Use user scope only when you intentionally want content available across
projects:

```bash
npx @indium-ai-labs/agentkit install --scope=user --target=codex
```

If `--target` is omitted, the CLI detects agent directories that already exist
inside the chosen scope. It fails with guidance when no target is detected.
Installing into every supported agent requires the explicit `--target=all`
flag.

## Installation model

Four independent inputs control every installation:

| Input | Meaning | Default |
| --- | --- | --- |
| Command | `install` for the bundle or `add <name>` for one artifact | required |
| Scope | `project` or `user` | `project` |
| Destination | Current project or `--project-dir=<path>` | current directory |
| Target | One agent, a comma-separated list, auto-detection, or explicit `all` | `auto` |

The npm CLI creates durable copies by default because links into a temporary
`npx` cache can break later. Use `--mode=link` only when you intentionally want
the destination to follow a local agentkit checkout. Existing files that are
not an exact copy or an agentkit link are reported and left untouched.

To upgrade copies installed by an earlier version, rerun the same command with
`--force`. It replaces only skills, subagents, and Cursor rules named after
agentkit content, and never replaces `AGENTS.md` or `CLAUDE.md`:

```bash
npx @indium-ai-labs/agentkit install --target=claude --force
```

Items marked internal in `CATALOG.md` apply only to this repository and are left
out of the `install` bundle; `add <name>` still installs one explicitly.

Project-context files follow the selected architecture:

| Target | Project content | Project context |
| --- | --- | --- |
| Claude Code | `.claude/skills`, `.claude/agents` | `CLAUDE.md` |
| Codex | `.codex/skills` | `AGENTS.md` |
| Gemini CLI | `.gemini/skills`, `.gemini/agents` | `AGENTS.md` |
| Antigravity | `.antigravity/skills`, `.antigravity/agents` | `AGENTS.md` |
| Cursor | generated `.cursor/rules/*.mdc` | `AGENTS.md` |
| OpenCode | `.opencode/skills` | `AGENTS.md` |

User-scoped installs write only to the selected tool directory beneath the
user home and never create project-context files.

### More examples

```bash
# Multiple explicit targets in one project
npx @indium-ai-labs/agentkit install --target=codex,cursor

# One Claude subagent in one project
npx @indium-ai-labs/agentkit add reviewer --target=claude

# Explicitly install everywhere in the user scope
npx @indium-ai-labs/agentkit install --scope=user --target=all

# Show every option and the active package version
npx @indium-ai-labs/agentkit --help
```

A selected subagent fails clearly when its target has no native subagent
installation path. Portable skills remain usable without subagents.

## Local checkout installers

The Bash and PowerShell wrappers use links by default for repository
development. Passing a project directory uses project scope only:

```bash
# macOS/Linux
./scripts/install.sh /path/to/project codex

# Windows PowerShell
.\scripts\install.ps1 -ProjectDir C:\path\to\project -TargetIde codex
```

Their advanced options map to the canonical Python installer:

```bash
python scripts/install.py \
  --scope project \
  --project-dir /path/to/project \
  --target cursor \
  --item systematic-debugging \
  --mode copy
```

Creating links on Windows requires Developer Mode or an Administrator shell.
The installer reports a clear remediation message if link creation fails.

Inspect exactly the boundary you installed:

```bash
python scripts/check_install.py \
  --project /path/to/project \
  --target codex \
  --item systematic-debugging \
  --mode copy
```

## Architecture

The repository uses two open, cross-agent formats:

- `SKILL.md` is a task-triggered capability with `name` and `description` YAML
  frontmatter plus a Markdown workflow. Claude Code, Codex, OpenCode, Gemini
  CLI, and Antigravity discover it natively.
- `AGENTS.md` is always-loaded project context. Codex, Cursor, Gemini CLI,
  Antigravity, Copilot, Aider, Windsurf, and Zed read it natively. The root
  file governs this repository; consumer projects receive the neutral
  `templates/AGENTS.md`. Claude receives the same context as `CLAUDE.md`.

Cursor does not natively discover `SKILL.md`. The dependency-free builder
converts each selected skill to `.cursor/rules/<name>.mdc`, preserving the
description and Markdown body with `alwaysApply: false`.

Subagents do not yet have a unified cross-tool schema. Agentkit uses Claude
Code-compatible frontmatter (`name`, `description`, `tools`, and `model`) as
the portable source shape. Most subagents are read-only reviewers and
investigators; a few implementers (`backend-builder`, `frontend-builder`,
`test-writer`, `doc-writer`) declare `Edit` and `Write` and change only the paths
the parent assigns. `ARCHITECTURE.md` lists each role.

## Repository layout

```text
indium-agentkit/
|-- AGENTS.md
|-- CATALOG.md
|-- agents/
|-- skills/
|-- templates/
|   |-- AGENTS.md
|   |-- skill.md
|   |-- subagent.md
|   `-- handoffs/
|-- scripts/
|   |-- cli.js
|   |-- install.py
|   |-- install.sh
|   |-- install.ps1
|   `-- build_cursor_rules.py
|-- tests/
`-- .github/workflows/validate.yml
```

## Adding content

Create skills at `skills/<name>/SKILL.md` and subagents at
`agents/<name>.md`, starting from `templates/skill.md` and `templates/subagent.md`
or `scripts/scaffold_content.py`. The authoring standard is in
`skills/author-agentkit-content/SKILL.md`, and `scripts/validate_content.py`
enforces it: trigger-focused descriptions, size limits, resolvable
cross-references, no repository-only script references, and no destructive
commands without an approval gate. Follow `CONTRIBUTING.md`, regenerate
`CATALOG.md`, and keep skills executable by a single agent even when delegation
can accelerate them.

## Validation

```bash
python scripts/generate_catalog.py
python scripts/diff_catalog.py
python scripts/validate_content.py
python scripts/validate_handoff.py --templates-dir templates/handoffs
python -m unittest discover -s tests -v
python scripts/build_cursor_rules.py --skills-dir skills --out-dir .cursor/rules
```

CI uses one workflow run per event. Superseded runs are cancelled, Bash smoke
coverage shares the Linux validation job, and the higher-cost Windows smoke job
runs only when installer-related files change.

See `CATALOG.md` for the generated inventory, `docs/compatibility.md` for the
support matrix, and `SECURITY.md` for distribution guidance.
