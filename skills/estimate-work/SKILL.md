---
name: estimate-work
description: "Estimate the scope, effort, and risk of a technical task by inspecting the affected code, slicing the work, giving three-point ranges per slice, and combining them into an honest range with stated assumptions. Use when someone asks how big, how long, or how risky a change is. Not for producing the implementation plan itself (use the plan-change skill)."
---

# Estimate Work

Give an estimate that is grounded in the code and honest about uncertainty: a
range with a confidence level and the assumptions behind it, never a single
precise number presented as fact.

## When to use

- "How long will this take?", "Is this a small or large change?", "What are the
  risks in migrating X?"
- Sizing work for a roadmap, a sprint, or a go or no-go decision.

## When not to use

- A step-by-step implementation plan is needed: use the `plan-change` skill (an
  estimate can be part of it).
- The uncertainty is too large to estimate: run the `prototype-spike` skill first.

## Inputs to gather

- The request, its scope, and what "done" means (tested, deployed, documented).
- **Who does the work:** an agent in this session, or a human team. Agent effort,
  human effort, and calendar time differ; say which one you estimate.
- The affected code, found by searching: modules, interfaces, schemas, tests,
  and their current coverage.
- **Reference history** where available: similar past changes in this repository
  (`git log --stat` on the affected paths, merged pull requests that touched them,
  and how large and how long they were).

## Workflow

1. **Inspect the impact.** Find the entry points, callers, data model, and tests
   affected. Note unfamiliar or untested areas; they drive risk.
2. **Slice the work** into pieces that can be delivered and verified separately,
   for example: schema and data migration, core logic, interfaces or API, UI, rollout
   and documentation. Skip slices that do not apply.
3. **Estimate each slice with three points**: optimistic O (things go right),
   most likely M, pessimistic P (realistic bad case, not catastrophe). Anchor the
   numbers to the reference history where you have it.
4. **Adjust for known risks per slice** by revising O, M, and P directly (for
   example a live data migration or an untested legacy module widens P). Name the
   reason for every adjustment rather than applying a generic multiplier.
5. **Combine** (formulas below) into a total range and a confidence statement.
6. **Check the spread.** If a significant slice has P more than about three times
   M, the uncertainty is too high for a useful estimate; recommend a spike for that
   slice and estimate the rest.
7. **Identify the critical path and dependencies** on other people, reviews,
   environments, or approvals, which often dominate calendar time.

## Combining three-point estimates

For each slice, the PERT approximation gives:

- mean = (O + 4M + P) / 6
- standard deviation = (P − O) / 6

For the total, add the means. If the slices are roughly independent, the total
standard deviation is the square root of the sum of the slice variances (each
variance is the standard deviation squared). Correlated risks (one shared unknown
affecting several slices) make the true spread wider than this; say so when it
applies.

Report a one-sided upper bound: about 84% confidence at mean + 1 × sd, 90% at
mean + 1.28 × sd, 95% at mean + 1.645 × sd. These rely on a normal approximation
that is rough for small numbers of slices, so round the results and present them
as a range.

Example with two slices, in hours: schema migration O=4, M=8, P=20 gives mean 9.3
and sd 2.7; API changes O=3, M=6, P=12 gives mean 6.5 and sd 1.5. Total mean 15.8,
total sd √(2.7² + 1.5²) ≈ 3.1, 90% upper bound ≈ 15.8 + 1.28 × 3.1 ≈ 19.8. Report
"about 16 hours, likely under 20, assuming the backfill fits in batches".

## Guardrails

- Do not output numbers without inspecting the affected code first.
- Never present an estimate as a commitment; it is planning information.
- Make every assumption explicit; an estimate without assumptions cannot be checked.

## Verification

Re-read the slices against the request: every requirement maps to a slice, and
every slice maps to code you inspected. Confirm the arithmetic.

## Report

- **Estimate:** the range, its confidence, and the unit (agent effort, human effort,
  or calendar time).
- **Slices:** a table with O, M, P, mean, and the main risk for each.
- **Assumptions and unknowns:** each with its effect on the range.
- **Critical path and external dependencies.**
- **Recommendation:** proceed, spike first (and on what), or split the work.

## Optional delegation

The `estimator` subagent can produce an independent estimate from the same inputs;
compare the two and explain any large difference.
