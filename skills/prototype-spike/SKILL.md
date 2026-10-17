---
name: prototype-spike
description: "Answer one technical question with a small, time-boxed, throwaway experiment that produces measured evidence and a go, conditional-go, or no-go recommendation before committing to an approach. Use when feasibility, performance, or integration behavior of a library, service, or design is uncertain. Not for production implementation (use the plan-change or test-first-change skill)."
---

# Prototype Spike

Reduce uncertainty cheaply. A spike answers a specific question with evidence,
then gets thrown away; its output is a decision and the facts behind it, not code
to ship.

## When to use

- "Can library X do Y within our constraints?", "How fast is approach A versus B?",
  "Does this API behave the way the docs claim?"
- An estimate or plan is blocked on an unknown.

## When not to use

- The approach is known and needs building: use the `plan-change` or
  `test-first-change` skill.
- Measuring an existing system's bottleneck: use the `performance-optimization` skill.

## Inputs to gather

- **The question**, phrased so evidence can answer it ("Can DuckDB aggregate our
  100 MB CSV export in under 500 ms on a CI runner?").
- **Decision criteria, agreed with the user up front:** what result means go,
  what means no-go, and what means go only under conditions. Do not invent the
  thresholds yourself; propose them and confirm.
- **The time box,** expressed in something you can track: a number of
  experiment iterations, or a rough budget of tool calls, as well as wall time
  if the user cares.
- **Representative inputs:** real-shaped sample data or a sandbox account, never
  production data or credentials.

## Workflow

1. **Write the hypothesis and criteria** in the report skeleton before writing code.
2. **Isolate the experiment.** Use a scratch directory outside the source tree
   (the system temporary directory, or a gitignored path the project already uses)
   so nothing leaks into commits. Record its location.
3. **Build the smallest thing that tests the riskiest assumption.** Skip error
   handling, tests, and polish unless they affect the answer.
4. **Measure honestly.** Warm up, repeat runs (at least five), and report the
   median and spread rather than one number. Use measurement tools suited to the
   question: wall-clock timers for latency, the OS or runtime's peak-memory report
   for memory. In Python, `tracemalloc` counts only Python allocations, not the
   whole process or native libraries.
5. **Record integration friction** you hit: confusing APIs, missing features,
   license terms, operational burden. These often decide the outcome more than
   speed does.
6. **Stop at the time box** even if the answer is "unclear"; report what you
   learned and what the next experiment would be.
7. **Decide** against the agreed criteria: `GO`, `CONDITIONAL_GO` (with the
   conditions), or `NO_GO`, and list alternatives considered.
8. **Clean up with consent.** Keep the scratch files until the findings are
   written down, then ask before deleting them. If the user wants to keep the
   code, move it somewhere clearly marked as a prototype.

## Guardrails

- Never commit spike code to production paths or merge it as-is.
- Never use production data, credentials, or shared environments for the
  experiment without explicit approval.
- Do not install new dependencies into the project to run a spike; install into
  the scratch environment, and ask first if that is not possible.
- Report negative and inconclusive results as clearly as positive ones.

## Verification

- The measurements are reproducible: the exact commands, versions, inputs, and
  machine are recorded.
- The decision follows from the agreed criteria, not from new criteria chosen after
  seeing the results.

## Report

```markdown
# Spike: <question>

**Decision:** GO | CONDITIONAL_GO | NO_GO
**Criteria (agreed before running):** <go / no-go thresholds>

## Setup
<versions, machine, data shape, scratch location>

## Results
| Variant | Runs | Median | Spread | Notes |
|---------|------|--------|--------|-------|

## Friction and risks
- ...

## Recommendation and next step
<what to build, or the next experiment, and what remains unknown>
```

## Optional delegation

The `docs-researcher` subagent can check version-exact documentation for the
candidate libraries while you build the experiment.
