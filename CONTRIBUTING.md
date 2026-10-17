# Contributing content

The full authoring standard lives in
[`skills/author-agentkit-content/SKILL.md`](skills/author-agentkit-content/SKILL.md).
Start new content from [`templates/skill.md`](templates/skill.md) or
[`templates/subagent.md`](templates/subagent.md), or run
`scripts/scaffold_content.py`.

## Skills

Create one directory per skill at `skills/<skill-name>/SKILL.md`. Use a
lowercase hyphenated directory name that exactly matches frontmatter `name`.
Keep skill frontmatter limited to `name` and `description`. Write the
description as what the skill does, when to use it, and what it is not for,
because agents select skills from it.

Keep the body short and standalone: when to use, inputs to gather, workflow,
guardrails, verification, and report. Aim for 80 to 250 lines. A skill may
suggest subagent delegation, but it must not require it, and it must work in
Cursor, which receives only the SKILL.md body.

Content runs in consumer repositories. Do not reference this repository's
`scripts/` or `templates/handoffs/`, never instruct an agent to discard work it
did not create, and require explicit approval before destructive, irreversible,
or production actions.

Add scripts or references only when they make the workflow more reliable or
avoid repeated work. Keep scripts portable, dependency-free when practical, and
inside the skill directory. Do not copy third-party content without confirming
its license and recording its provenance.

## Subagents

Create subagents as `agents/<name>.md` with `name`, `description`, `tools`, and
`model` frontmatter. Define a narrow responsibility, the inputs the parent must
provide, and a clear output format. Choose one of two roles:

- **Read-only specialists** declare `tools: Read, Grep, Glob, Bash`, use Bash
  only for non-mutating commands, and end the description with `Read-only.`
- **Write-scoped implementers** declare `tools: Read, Grep, Glob, Edit, Write, Bash`,
  edit only the paths the parent assigns, and end the description with
  `Edits only assigned paths.`

Prefer a read-only specialist unless the role exists to make changes.

## Using agentkit in this repository

`npx @indium-ai-labs/agentkit` fails inside this checkout because npm treats the
checkout as the requested package and looks for its command in a
`node_modules/.bin` directory that does not exist. Install from the checkout
instead:

```bash
python scripts/install.py --scope project --project-dir . --target claude --mode link
python scripts/install.py --scope project --project-dir . --target claude --mode link --item author-agentkit-content
```

Links follow your edits. On Windows they need Developer Mode, so use
`--mode copy` there and rerun with `--force` after changing content. Omit
`--include-context`, because the root `AGENTS.md` already provides this
repository's context. Git ignores the installed `.claude/skills/` and
`.claude/agents/`.

## Required checks

Run these commands before committing:

```bash
python scripts/validate_content.py
python scripts/validate_handoff.py --templates-dir templates/handoffs
python scripts/generate_catalog.py
python scripts/diff_catalog.py
python -m unittest discover -s tests -v
python scripts/build_cursor_rules.py --skills-dir skills --out-dir .cursor/rules
```

Installer changes must also preserve the scope contract: project installs may
write only below the selected project, user installs may write only below the
selected home, and `add <name>` may install only that artifact. Add regression
coverage in `tests/test_install.py` and `tests/test_cli.py` for changes to these
boundaries.

Commit frequent, scoped, coherent units of completed work. Use concise,
professional imperative subjects that say what changed, such as `Add handoff
template validation`; avoid vague or phase-based subjects. Catalog changes
belong in the same commit as the content change. Push each completed scoped
commit directly to `origin/main` as required by the root `AGENTS.md`.

Use `scripts/check_install.py` to diagnose an installation without changing it.
Use `scripts/codex_delegate.py` to turn a portable `agents/<name>.md` role into
a bounded packet for a native Codex orchestrator; it must remain side-effect
free and must not call a model directly.
