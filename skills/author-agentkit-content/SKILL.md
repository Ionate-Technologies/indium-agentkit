---
name: author-agentkit-content
description: "Create or revise indium-agentkit skills, subagents, templates, and their validation and catalog files to the repository authoring standard. Use when adding, rewriting, or reviewing content in this agentkit repository. Internal to this repository; not for consumer projects."
---

# Author Agentkit Content

Write skills and subagents that a coding agent can load cheaply, trigger
reliably, and follow safely in any consumer repository. This skill is the
authoring standard for this repository; `templates/skill.md` and
`templates/subagent.md` are the starting skeletons.

## When to use

- Adding a skill under `skills/<name>/SKILL.md` or a subagent under `agents/<name>.md`.
- Rewriting, trimming, or reviewing existing content against the standard.
- Changing templates, validators, the catalog, or the Cursor conversion.

## When not to use

- Work in a consumer project that installed agentkit. This skill is excluded from
  the default `install` bundle for that reason.

## Principles

1. **Every line must change agent behavior.** Cut ceremony: JSON input schemas,
   "invocation modes", LaTeX restatements of prose, emoji headings, and
   boilerplate rollback scripts. Agents receive natural-language tasks, not
   manifests.
2. **Portable by default.** Content runs in someone else's repository. Do not
   reference this repository's `scripts/` or `templates/handoffs/`; consumers do
   not receive them. Discover commands from the consumer's `AGENTS.md`,
   `CLAUDE.md`, package scripts, or `Makefile`.
3. **Safe by default.** Never instruct an agent to discard work it did not create
   (`git checkout -- <dir>`, `git reset --hard`, `rm -rf` on variables), or to
   take production, destructive, irreversible, or outward-facing actions without
   asking. Never weaken a test or check to make work pass.
4. **Correct or absent.** Code examples must run as written (syntax-check them)
   and be marked illustrative. No invented scripts, flags, numbers, or SLAs;
   present thresholds as "use the project's SLO; for example ...".
5. **Single-agent complete.** A skill may suggest delegation but must work for
   one agent alone, including in Cursor, which receives only the SKILL.md body.

## Skill standard

**Frontmatter:** only `name` (matching the directory) and `description`. Quote
the description. Do not use `<` or `>` in it.

**Description** (80 to 600 characters): what it does, then when to use it, then
what it is not for. It drives automatic triggering, so name the situations and
phrases that should select it.

```text
Investigate a bug, failing test, or regression by reproducing it and testing
hypotheses before fixing. Use when behavior is wrong and the cause is unknown.
Not for planned refactors (use the refactor-code skill).
```

**Body** (aim for 80 to 250 lines; 400 is the hard cap), in this order:

1. Title and a one- or two-sentence statement of outcome and stance.
2. `## When to use` and `## When not to use`, routing to siblings by name.
3. `## Inputs to gather`: a plain list; discover first, ask only when ambiguous.
4. `## Workflow`: numbered steps with decision points.
5. `## Guardrails`: the standard safety lines plus domain-specific ones.
6. `## Verification`: what to check and what passing looks like; project
   commands only, each run separately, never `cmd1 || cmd2` fallbacks.
7. `## Report`: the fields to return, including what was not verified.
8. `## Optional delegation`: which subagent helps, if any.

Additional rules:

- **Cross-references:** write "the `name` skill" or "the `name` subagent" so the
  validator can resolve them. Route only to content that exists.
- **Handoffs:** when a skill produces a handoff document, inline its required
  headings in the Report section as a fenced markdown block, preceded by an
  HTML comment such as `<!-- handoff: api-contract -->`. The headings must match
  `REQUIRED_HEADINGS` in `scripts/validate_handoff.py` plus the five Handoff
  labels.
- **Long reference material** may live in `skills/<name>/references/*.md`.
  Mention it as plain path text, not a Markdown link. The body must still work
  without it, because Cursor receives only the body.
- **Bundled scripts** go in `skills/<name>/scripts/`, must be dependency-free and
  tested, and must be referenced by that path.
- **No README** inside skill directories; the SKILL.md is the documentation.

## Subagent standard

**Frontmatter:** exactly `name`, `description`, `tools`, `model` (`inherit`
unless there is a reason).

**Description:** role, then "Use proactively when ..." or "Use when ...", then
exactly one of:

- `Read-only.` with `tools: Read, Grep, Glob, Bash`
- `Edits only assigned paths.` with `tools: Read, Grep, Glob, Edit, Write, Bash`

Add `WebFetch, WebSearch` only for roles whose job is external research.

**Body** (80 to 180 lines; 250 is the hard cap): follow `templates/subagent.md`:
scope (allowed and prohibited, including the Bash rule), when to use and not,
trust boundary, inputs from the parent as a short list, procedure, output.

**Shared vocabulary** across every subagent:

- Status: `PASSED`, `FAILED`, `BLOCKED`, `PARTIAL`.
- Severity: `critical`, `high`, `medium`, `low`, `info`, each with a confidence
  of `high`, `medium`, or `low`.
- Findings cite `path:line` relative to the repository root and are verified
  before they are reported.

Do not add fake budgets ("15 minutes", "256 MB"), telemetry exports, checkpoint
files, or "enterprise lifecycle" checklists. Keep only limits the agent can
actually observe, such as "stop after two failed attempts and report".

## Workflow

1. **Check for overlap.** Read `CATALOG.md` and the closest existing items.
   Extend or sharpen an existing item instead of adding a near-duplicate.
2. **Scaffold.** `python scripts/scaffold_content.py skill <name> --description "<...>"`
   or `... agent <name> --description "<...>" [--tools "<...>"]`. It refuses to
   overwrite existing files.
3. **Write** to the standard above. For a rewrite, keep the domain substance and
   correct it; remove only ceremony.
4. **Self-review** the diff against this checklist:
   - Description: triggers named, sibling routing correct, 80 to 600 characters.
   - Every command exists, every flag is current, every path is portable.
   - No destructive step runs without an explicit approval point.
   - Code examples compile or parse; numbers are sourced or labeled examples.
   - Cross-references resolve to existing skills and subagents.
5. **Validate and regenerate** (commands below). Catalog changes belong in the
   same commit as the content change.
6. **Commit** a coherent unit with a concise imperative subject, for example
   `Rewrite review-change skill to verify findings before reporting`, then push
   as the root `AGENTS.md` requires.

## Verification

Run each command separately from the repository root:

```bash
python scripts/validate_content.py
python scripts/validate_handoff.py --templates-dir templates/handoffs
python scripts/generate_catalog.py
python scripts/diff_catalog.py
python scripts/build_cursor_rules.py --skills-dir skills --out-dir .cursor/rules
python -m unittest discover -s tests -v
```

For changes to installers, also preserve the scope contract described in
`CONTRIBUTING.md` and add coverage in `tests/test_install.py` and
`tests/test_cli.py`.

## Guardrails

- Stage explicit paths; do not sweep unrelated files into a content commit.
- If validation fails, fix the content. Do not loosen a validator to pass
  without a separate, justified commit that updates its tests.
- Do not copy third-party content without confirming its license and recording
  its provenance.

## Report

- Items created or changed, with before and after line counts.
- Description changes and any routing added or removed.
- Each validation command and its result.
- Commit subject and whether it was pushed.
