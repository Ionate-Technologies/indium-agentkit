---
name: plan-change
description: "Turn a feature request, bug report, refactor, or technical proposal into an implementation-ready plan with goals, non-goals, acceptance criteria tied to tests, affected code, ordered reviewable steps, risks, and rollback. Use when a change is non-trivial, spans several files, or needs agreement before coding. Not for trivial one-line fixes or for investigating an unknown bug (use the systematic-debugging skill)."
---

# Plan Change

Produce a plan another engineer or agent could execute without guessing, grounded
in the code as it is today. Planning does not modify application code. Scale the
plan to the change: a small change gets a short plan.

## When to use

- A feature, refactor, migration, or proposal that touches several files,
  modules, or teams, or carries risk to data, security, or compatibility.
- The user asks for a plan, design, or approach before implementation.

## When not to use

- The cause of a bug is unknown: use the `systematic-debugging` skill first.
- Only an effort estimate is needed: use the `estimate-work` skill.
- An experiment is needed to choose an approach: use the `prototype-spike` skill.
- Designing an API contract or data schema in depth: use the `api-design` or
  `database-design` skill, then reference their output here.

## Inputs to gather

- The request and its motivation: issue, ticket, conversation, or proposal.
- `AGENTS.md` or `CLAUDE.md` for conventions and commands.
- The code that will change and the code that calls it, found by searching the
  repository rather than assumed.
- Constraints: compatibility promises, deadlines, performance targets, rollout
  rules, and anything the user said is out of bounds.

Ask clarifying questions only when the answer would change the plan and cannot
be found in the repository. State assumptions explicitly instead of guessing
silently.

## Workflow

1. **Frame the change.** Write the goal (the outcome, not the implementation),
   non-goals (what is deliberately excluded, to prevent scope creep), and
   constraints.
2. **Map the impact from the code.** Locate entry points, affected modules,
   public interfaces (API shapes, database schemas, events, CLI flags, exported
   functions), callers, configuration, and the tests that cover each area. Cite
   paths. Note anything that surprised you, because surprises are risks.
3. **Choose the approach.** If there is a real choice, compare two or three
   options in a few lines each (complexity, risk, reversibility) and recommend
   one. If one option is clearly right, say so and move on.
4. **Write acceptance criteria** as observable behavior, each paired with how it
   will be verified (a named test to add or update, a command, or a manual
   check). A criterion nobody can verify is a wish, not a criterion.
5. **Order the steps** so each is independently reviewable and leaves the system
   working, typically: contracts and schema (expand, never contract first), core
   logic with unit tests, integration and interfaces, then documentation, flags,
   and cleanup. Name the files each step touches.
6. **Assess risks and rollback.** Security, data migration, compatibility with
   running clients, performance, and operational impact. For each real risk give a
   mitigation. State how to roll back or disable the change (feature flag, revert,
   down migration) and which steps are irreversible.
7. **Present the plan for approval** in the form the host expects (in the
   conversation, or in the plan file or mode the environment provides). Do not
   start implementation until the user approves when approval was requested or
   the change is risky.

## Plan format

```markdown
# Plan: <title>

## Goal
<one or two sentences>

## Non-goals
- ...

## Context and constraints
- <facts from the code, with paths>

## Approach
<recommended option and why; alternatives in one line each if relevant>

## Acceptance criteria
1. <observable behavior> - verified by <test or command>

## Steps
1. <step> - files: `path/a`, `path/b`
2. ...

## Risks and rollback
- <risk> - mitigation
- Rollback: <how>; irreversible steps: <list or none>

## Open questions
- ...
```

## Guardrails

- Do not edit application code while planning. Writing the plan document itself
  is fine where the host expects it.
- Ground every claim about the code in something you read; mark guesses as
  assumptions.
- Never plan a breaking change to a public contract without a migration or
  deprecation path and explicit approval.

## Verification

Before presenting, check the plan against the code: every file, function, and
command it names exists; every acceptance criterion has a verification method;
every step leaves the build and tests passing; non-goals and steps do not
overlap.

## Report

The plan in the format above, plus a one-line summary of the recommendation and
any decision the user must make.

## Optional delegation

For a large plan, the `explorer` subagent can map unfamiliar areas in parallel,
and the `plan-reviewer` subagent can critique the finished plan against the code
before you present it.
