---
name: flaky-test-triage
description: "Diagnose and fix tests that pass and fail on the same code: measure the flake rate, classify the cause (timing, ordering, shared state, environment, concurrency, external dependencies), fix the root cause, and quarantine only with a tracked issue. Use when a test fails intermittently locally or in CI, or a retry makes CI green. Not for tests that fail consistently (use the systematic-debugging skill)."
---

# Flaky Test Triage

A flaky test is a bug, either in the test or in the code. Find which, fix the
cause, and prove the fix statistically. Retrying until green is not a fix.

## When to use

- A test fails sometimes on unchanged code, locally or in CI.
- CI passes only after re-runs, or a test was marked "retry" or "skip" for flakiness.

## When not to use

- The test fails every time: use the `systematic-debugging` skill.
- The whole CI job fails intermittently for infrastructure reasons (runner,
  network, cache): delegate to the `ci-verifier` subagent.

## Inputs to gather

- The test's name, file, and recent failure output from CI or local runs.
- How often it fails and where (CI only, local only, one operating system, one
  parallel shard). CI history or the test reporter's flaky-test data helps.
- The test runner's options for repetition, ordering, seeding, and isolation.

## Workflow

1. **Measure.** Run the test alone in a loop and count failures, for example 50 to
   200 runs. Then run it with its neighbors and in the full suite, because some
   flakes only appear with other tests.

   ```bash
   # Illustrative; adapt to the project's runner.
   for i in $(seq 1 100); do npx vitest run path/to/file.test.ts -t "name" || echo "FAIL $i"; done
   python -m pytest tests/test_jobs.py::test_retry --count=100   # needs the pytest-repeat plugin
   go test ./jobs -run '^TestRetry$' -count=200
   ```

   Record the failure rate p. If you cannot reproduce it locally, collect CI logs
   from several failures and compare them.
2. **Classify the cause** using the failure output and how the rate changes under
   different conditions:
   - **Timing:** fixed sleeps, timeouts too tight for slow runners, polling without
     a deadline, animations. Fails more under load (`--parallel`, CPU stress).
   - **Order dependence and shared state:** relies on another test's data, global
     variables, singletons, caches, environment variables, or files left behind.
     Fails when run alone, or only in a particular order (randomize or reverse the
     order to check).
   - **Concurrency:** races in the code under test or in test setup; unawaited
     promises; parallel tests sharing a database, port, or temp directory.
   - **Time and randomness:** the current date, time zones, daylight saving, month
     ends, unseeded random data, unordered collections (map or set iteration,
     `SELECT` without `ORDER BY`).
   - **Environment:** locale, operating system path differences, available memory,
     dependency versions differing between CI and local.
   - **External dependencies:** real network calls, third-party sandboxes, shared
     staging services.
3. **Prove the hypothesis.** Make the failure deterministic: force the ordering,
   inject the slow path, freeze the clock at the edge value, fix the random seed.
   A cause you can trigger on demand is a cause you understand.
4. **Fix the root cause**, preferring in this order:
   - Fix the code under test if it has a real race or ordering bug (that is a
     product bug; treat it with the `systematic-debugging` skill's rigor).
   - Make the test deterministic: wait on conditions instead of sleeping, use the
     project's fake clock and seeded randomness, isolate data per test, sort before
     comparing, mock the network at the boundary.
   - Give parallel tests unique resources (database schema, port, temp directory).
5. **Verify statistically.** Rerun the loop after the fix. To be 95% confident a
   failure with rate p is gone, you need n ≥ ln(0.05) / ln(1 − p) clean runs:
   about 59 runs at p = 0.05 and about 299 at p = 0.01. Also run the full suite.
6. **If you cannot fix it now**, quarantine visibly: mark it with the runner's
   skip or quarantine mechanism, link a tracked issue with the evidence gathered,
   and keep running it in a non-blocking job if the project supports that. Ask the
   user before quarantining a test in a required check.

## Guardrails

- Never add blanket retries, longer sleeps, or a skip as the fix without stating
  that it is a mitigation and leaving a tracked issue.
- Never delete a flaky test or weaken its assertions to make it pass.
- Do not change CI configuration (retries, required checks) without approval.

## Verification

- Failure rate measured before the fix, and the number of clean runs after it, with
  the commands used.
- The deterministic reproduction from step 3 now passes.
- The full suite passes.

## Report

- Test, failure rate before and after, and runs performed.
- Cause category and the evidence that proved it.
- The fix (test, code, or both) and why it removes the cause.
- Any quarantine, with the issue link.

## Optional delegation

The `debugger` subagent can run the repetition loops and order experiments in
parallel; confirm its reproduction before applying a fix.
