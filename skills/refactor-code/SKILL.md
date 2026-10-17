---
name: refactor-code
description: "Restructure code (extract, inline, rename, move, split, simplify, decouple) to improve clarity and maintainability while preserving observable behavior, proven by tests run after every small step. Use when code works but is hard to change, read, or test. Not for changing behavior or fixing bugs (use the test-first-change or systematic-debugging skill)."
---

# Refactor Code

Improve the structure of working code in small, verified steps without changing
what it does. If behavior must change, that is a separate change.

## When to use

- Code is duplicated, tangled, too long, poorly named, or hard to test, and the
  user wants it cleaned up.
- A planned feature would be easier after restructuring (refactor first, then
  build the feature in a separate change).

## When not to use

- Behavior should change: use the `test-first-change` skill.
- A bug needs fixing: use the `systematic-debugging` skill. Do not hide a fix
  inside a refactor.
- Large mechanical changes across many files (API renames, import moves): use the
  `ast-manipulation-codemods` skill.
- Tightening static types across a codebase: use the `strengthen-types` skill.
- Removing a stale feature flag and its dead branch: use the
  `feature-flag-lifecycle` skill.

## Inputs to gather

- The target code and its goal ("extract validation from `OrderService` so it can
  be reused").
- The public surface that must not change: exported names and signatures, HTTP
  or CLI contracts, events, error types and messages, side effects, logs other
  systems parse.
- The tests that cover it, and the commands to run them.

## Workflow

1. **Establish a green baseline.** Run the tests covering the target. If they fail
   before you start, stop and report; refactoring on red hides breakage.
2. **Check coverage of the behavior you will touch.** If tests are thin, first add
   characterization tests that pin current behavior at a public seam, including
   edge cases and error paths. Commit or checkpoint them separately when the user
   wants commits. The `test-writer` subagent can do this.
3. **Plan small steps.** Each step is one named refactoring: extract function,
   inline variable, rename symbol, move module, introduce parameter object,
   replace conditional with polymorphism, split file. Order them so the code
   compiles and tests pass after every step.
4. **Apply one step at a time.** Prefer the language server or IDE refactoring
   (rename symbol, move file, extract) over hand edits; they update references
   reliably. Then run the focused tests.
   - If a step breaks tests, undo that step's edits (your own edits only), work
     out why, and try a smaller step. Do not "fix forward" by changing tests.
5. **Clean up** unused imports, dead code made unreachable by your changes, and
   formatting through the project's formatter.
6. **Run the full suite**, lint, and type-check as separate commands.
7. **Review the final diff** as a whole: public signatures unchanged, no new
   behavior, no stray edits.

## Tests and assertions

- Assertions about observable behavior never change during a refactor. If one
  must change, you are changing behavior; stop and say so.
- Tests that are coupled to internals (mocks of private helpers, asserting call
  order of private functions) may need mechanical updates when you move those
  internals. Call each such change out in the report so a reviewer can confirm it
  does not weaken the test.

## Guardrails

- Keep refactoring separate from feature work, bug fixes, and dependency upgrades.
- Undo only edits you made in this session; never discard other uncommitted work.
- Preserve the public contract exactly, including error messages and log formats
  that other systems may depend on.
- Stop and ask if the refactor turns out to need a behavior or interface change.

## Verification

- Baseline and final runs of the same test commands, both green.
- Lint and type-check pass.
- A diff review confirms public signatures and contracts are unchanged.

## Report

- Goal and the sequence of refactorings applied.
- Characterization tests added, if any.
- Test changes made to internal-coupled tests, each with a reason.
- Baseline and final test results, plus lint and type-check results.
- Anything left for a follow-up (for example "behavior X looks wrong; not changed").
