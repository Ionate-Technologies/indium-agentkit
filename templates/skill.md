---
name: <skill-name>
description: "<What the skill does, in one sentence>. Use when <concrete triggers: phrases a user says or situations an agent recognizes>. Not for <adjacent task> (use the <other-skill> skill)."
---

# <Skill title>

<One or two sentences: the outcome this skill produces and the stance it takes,
for example "evidence before patch" or "design only, no implementation".>

## When to use

- <Trigger 1>
- <Trigger 2>

## When not to use

- <Adjacent task>: use the `<other-skill>` skill.
- <Independent review>: delegate to the `<agent-name>` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- <Input>: where to find it (`AGENTS.md`, manifests, existing code, tickets).

## Workflow

1. **<Step>.** <What to do, and how to decide when the situation varies.>
2. **<Step>.** <Adapt commands and paths to the project's conventions.>

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
- Never weaken a test, check, or threshold to make work pass.
- <Domain-specific guardrail.>

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- <What to verify, and what passing looks like.>

## Report

- **<Field>:** <content>
- **Not verified:** checks that could not run and why.

<!-- When the skill produces a handoff, inline its headings here as a fenced
markdown block preceded by an HTML comment naming the kind, for example
"handoff: api-contract". Consumers do not receive templates/handoffs/. -->

## Optional delegation

<Which subagent can run which part in parallel. The workflow above must stay
complete for a single agent.>
