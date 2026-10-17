---
name: systematic-debugging
description: "Investigate a bug, failing test, regression, unexpected output, or production issue by reproducing it, tracing the divergence, testing competing hypotheses, and locking the root cause with a regression test before fixing. Use when behavior is wrong and the cause is not yet proven. Not for planned refactors (use the refactor-code skill) or flaky tests (use the flaky-test-triage skill)."
---

# Systematic Debugging

Find and fix the root cause of a failure with evidence, not intuition. The stance
is **evidence before patch**: no production code changes until the failure
reproduces and at least one falsifiable hypothesis is on record.

## When to use

- A bug report, failing test, regression, wrong output, or crash with an unknown cause.
- A fix was attempted and the problem came back, or nobody can explain why it works.

## When not to use

- A test passes and fails on the same code: use the `flaky-test-triage` skill.
- An active production incident needs coordination first: use the
  `incident-triage` skill, then return here for root cause.
- The change is a planned restructuring with no defect: use the `refactor-code` skill.
- Repairing the data a fixed bug corrupted: use the `production-data-fix`
  skill.
- Memory growth in a long-running process: use the `memory-leak-investigation`
  skill.

## Inputs to gather

Discover from the repository and the report; ask only for what is missing.

- Observed versus expected behavior, impact, and when it started. If nobody can
  state the expected behavior, use the documented contract (tests, API schema,
  spec) and say so.
- Evidence: error messages, stack traces, logs, failing CI jobs, recent deploys.
- Runtime, versions, and the project's test and run commands from `AGENTS.md`,
  package scripts, or the `Makefile`.

## Workflow

1. **Observe.** Write one short statement each of observed behavior, expected
   behavior, and impact. List what is not yet known. Redact secrets and personal
   data from every log or payload you copy.
2. **Reproduce.** Build the smallest reliable failing signal: one test, one
   request, or one script, not the whole workload. Record the exact command,
   inputs, and environment.
   - Classify determinism: always, intermittent, or not yet reproduced.
   - For intermittent failures, run the reproduction in a loop and record the
     failure rate before trusting any conclusion (see Verification).
   - If it will not reproduce here, state which environmental factor blocks it
     and what would unblock it. Do not "fix" an unreproduced failure.
3. **Trace backward** from the failure, frame by frame or log line by log line,
   to the **divergence point**: the earliest place where an actual value differs
   from what the contract says it should be. Add temporary logs or assertions only
   where the trace goes dark, and track them so you can remove them.
4. **Hypothesize.** Write at least two competing hypotheses that each explain the
   divergence point, in falsifiable form: "If H is true, experiment E will show X;
   otherwise H is rejected." Order experiments by information gained per unit of
   cost (a one-line probe, a forced input, `git bisect` across recent commits).
   Prefer an experiment over an intuitive patch: a premature patch destroys the
   evidence you need.
5. **Identify the root cause** only when an experiment supports it. Name the exact
   line, state, configuration value, or input, and cite the experiment. Separate
   the trigger (the input that provokes it) from the defect (the missing guard).
   If evidence is insufficient, stop and report which hypotheses remain and what
   observation would decide between them.
6. **Lock it with a regression test** at a public seam (HTTP endpoint, exported
   function, CLI command) when the project has a harness. The test encodes the
   expected behavior, so run it against the unfixed code and confirm it fails for
   the root-cause reason, not a setup error.
7. **Fix minimally.** Make the smallest change that addresses the cause. Keep the
   diff small (as a guideline, tens of lines); justify anything larger in the
   report. No drive-by refactors, dependency upgrades, or formatting sweeps.
   Confirm the unmodified regression test now passes, rerun the original
   reproduction, then the focused and full suites. Remove all temporary
   instrumentation.
8. **Report** using the format below.

## Worked example: hypothesis register

Intermittent HTTP 500 on `POST /api/orders`, about 5% of requests at 50 requests
per second, never at 1 per second.

```markdown
| ID | Hypothesis (falsifiable)                                           | Experiment            | Result    |
|----|--------------------------------------------------------------------|-----------------------|-----------|
| H1 | Concurrent requests lock inventory rows in opposite order, so      | Query pg_locks during | CONFIRMED |
|    | pg_locks shows a wait cycle during failures                        | a failure burst       |           |
| H2 | The connection pool is exhausted, so failures track checkout waits | Overlay pool metrics  | REJECTED  |
| H3 | Retry middleware replays a consumed body, so failures carry        | Search 600 failure    | REJECTED  |
|    | body-hash mismatch warnings                                        | traces                |           |

Root cause: update_inventory_batch() locks rows in request order; the single-item
path locks in SKU order, creating a lock-ordering cycle. Trigger: concurrent carts
sharing two or more SKUs. Fix: sort keys before SELECT ... FOR UPDATE.
Regression test: 5 deadlocks in 100 rounds before the fix, 0 in 500 after.
```

## Guardrails

- Investigate before editing. Reproduce against local, staging, or replayed
  traffic; never run experiments that write to production data.
- Revert only your own temporary instrumentation and experiments. Never discard
  uncommitted work you did not create.
- Never edit the regression test to make it pass, and never declare "fixed"
  against a failure that was not reproduced.
- If the bug is a security defect, keep exploit details in the report; do not
  paste working payloads into shared logs or issue trackers.
- Optional parallel exploration is fine, but one agent must be able to finish
  this workflow alone.

## Verification

Use the project's own commands, run separately:

1. The original reproduction command shows the failure is gone.
2. The new regression test alone: failing output before the fix, passing after.
3. Type check, lint, and the focused suite, then the full suite.
4. Inspect `git diff` for leftover instrumentation (`console.log`, `print(`,
   `debugger`, `breakpoint(`) and secret-shaped strings.

For an intermittent failure with observed rate p, the number of clean runs
needed after the fix to be 95% confident the bug is gone is
n ≥ ln(0.05) / ln(1 − p). At p = 0.05 that is about 59 runs; at p = 0.01, about
299. Report the runs actually performed.

## Report

1. **Problem:** observed versus expected behavior, impact, severity.
2. **Reproduction:** command, determinism, measured failure rate.
3. **Root cause:** the defect with `path:line`, the confirming experiment, and the
   rejected hypotheses.
4. **Fix:** the diff and why it addresses the cause rather than the symptom.
5. **Regression test:** name, with red and green output.
6. **Verification:** each command and its result.
7. **Remaining uncertainty:** platforms, inputs, or rates not verified, and any
   follow-up monitoring.

## Optional delegation

The `debugger` subagent can reproduce and test hypotheses in parallel while you
work elsewhere; re-run its key experiment before acting on its conclusion. The
`test-writer` subagent can write the regression test once the cause is known.
