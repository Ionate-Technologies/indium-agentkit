---
name: test-first-change
description: "Implement a behavior change or bug fix test-first: write a failing test at a public seam, confirm it fails for the right reason, make the smallest change that passes, then refactor with the suite green. Use when the desired behavior can be stated as an executable test before coding. Not for exploratory spikes (use the prototype-spike skill) or unknown-cause bugs (use the systematic-debugging skill first)."
---

# Test-First Change

Drive a change with the red, green, refactor loop so the new behavior is proven
by a test that failed before the change and passes after it.

## When to use

- A new behavior, a rule change, or a bug fix whose expected behavior is clear.
- The user asks for TDD, or the change is risky enough that a failing test should
  come first.

## When not to use

- The approach itself is uncertain or throwaway: use the `prototype-spike` skill.
- The bug's cause is unknown: use the `systematic-debugging` skill, which ends in
  this same red-green step.
- Purely visual UI work where a test cannot express the requirement well; use
  component or end-to-end tests for behavior, and review visuals manually.

## Inputs to gather

- The behavior as input and expected output, error, or side effect.
- The test framework, file layout, naming, and fixtures, learned from `AGENTS.md`
  and three nearby tests.
- The command to run a single test and the full suite.

## Workflow

1. **State the behavior** in one sentence per case: "Given X, when Y, then Z."
   Include the error cases that matter.
2. **Choose the seam.** Test through the most public interface that exercises the
   behavior cheaply: an exported function, a service method, an HTTP handler, a
   CLI command, or a rendered component. Avoid testing private helpers; those
   tests break on every refactor.
3. **Red: write one failing test** for the first case, matching project style.
   Run it alone and read the failure. It must fail because the behavior is
   missing, not because of an import error, a typo, or broken setup. If it passes
   already, the behavior exists or the test is wrong; find out which before going on.
4. **Green: make the smallest production change** that passes the test. Resist
   adding behavior no test asks for. Rerun the single test, then the related tests.
5. **Repeat** red and green for each remaining case, one at a time.
6. **Refactor** names, duplication, and structure in both production and test
   code, rerunning the tests after each step. Behavior and assertions stay
   unchanged during refactoring.
7. **Run the full suite**, plus lint and type-check, as separate commands.

## Running a single test

Use the project's runner. Common forms:

```bash
npx vitest run path/to/file.test.ts -t "rejects passwords without a symbol"
npx jest path/to/file.test.ts -t "rejects passwords without a symbol"
python -m pytest tests/test_auth.py::test_rejects_password_without_symbol -q
go test ./auth -run '^TestRejectsPasswordWithoutSymbol$'
cargo test rejects_password_without_symbol
```

If the project wraps its runner in a package script, pass arguments through
(for example `npm test -- path/to/file.test.ts -t "..."`), and check how the
script forwards them.

## Example

```typescript
// Red: this fails until validatePassword enforces the rule.
it('rejects passwords without a symbol', () => {
  const result = validatePassword('Password123');
  expect(result.ok).toBe(false);
  expect(result.reason).toBe('missing_symbol');
});
```

The first run should fail on the assertion (`expected true to be false`). Failing
with `validatePassword is not defined` means the test is not yet testing the rule.

## Guardrails

- Never weaken, skip, or delete an assertion to get to green.
- Undo only your own edits when an approach fails; do not discard other
  uncommitted work in the tree.
- Keep refactoring separate from behavior changes; if a refactor needs a behavior
  change, go back to red.
- Tests must be deterministic: no real network, clock, or random values without
  the project's fakes or seeds.

## Verification

- The new tests failed before the change (keep the failing output) and pass after.
- The full suite, lint, and type-check pass, each run separately.
- The diff contains no unrelated changes.

## Report

- Behavior specified, with the test names.
- Red output (the key failing line) and green result.
- Production changes, by file.
- Full suite, lint, and type-check results.
- Cases deliberately not covered, and why.

## Optional delegation

The `test-writer` subagent can write the failing tests while you study the
production code; review that each test fails for the stated reason before
implementing.
