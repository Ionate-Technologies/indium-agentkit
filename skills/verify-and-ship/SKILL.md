---
name: verify-and-ship
description: "Verify finished changes with the project's own test, lint, type-check, and build commands, audit the diff for secrets and stray files, then commit, push, or open a pull request according to the repository's rules and the user's authorization. Use when work is done and needs to be checked and delivered. Not for reviewing someone else's change (use the review-change skill)."
---

# Verify and Ship

Prove that a finished change works, make sure only intended files are included,
and deliver it the way this repository expects. Never claim a check passed
without running it, and never push or publish without authorization.

## When to use

- "Run the checks and commit this", "ship it", "open a PR for these changes".
- Finishing a task before handing it back to the user.

## When not to use

- Reviewing a change for defects: use the `review-change` skill.
- Release preparation, versioning, and changelogs: use the `release-notes` skill
  and the `release-engineer` subagent.
- Production deployment: use the `deployment-safety` skill.
- Publishing a library or SDK to a package registry: use the `publish-library`
  skill.
- Repairing a bad Git state before shipping: use the `git-recovery` skill.

## Inputs to gather

- **Project rules.** Read `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and any
  pull-request template. Note required checks, commit message conventions,
  branch policy (direct to the default branch, or branches and pull requests),
  and generated files that must be regenerated in the same commit.
- **Commands.** Take test, lint, type-check, format, and build commands from
  those files, package scripts, the `Makefile`, or CI workflows. Prefer exactly
  what CI runs.
- **Authorization.** Whether the user asked you to commit, push, or open a pull
  request. If they did not say, verify and stop before committing, then ask.

## Workflow

1. **Review the working tree.** Run `git status` and `git diff --stat`. Confirm
   every changed and untracked file belongs to this task. Unrelated changes stay
   out of the commit; mention them to the user rather than reverting them.
2. **Regenerate derived files** the project requires (lockfiles, generated
   clients, catalogs, snapshots) using its documented commands, so they match
   the source in the same commit.
3. **Run the checks** one at a time, in CI order where known: format check,
   lint, type-check, unit tests, then build and broader tests. Record each
   command and its exit status. If a check fails:
   - Fix the cause if it is in scope, then rerun that check and everything after it.
   - If the failure predates your change, confirm by checking the default branch
     or asking, and report it instead of hiding it.
   - Never skip, disable, or weaken a check, test, or threshold to get green.
4. **Audit the diff** before staging:
   - `git diff --check` for whitespace errors and leftover conflict markers.
   - Debug output, commented-out code, temporary instrumentation, `TODO` notes
     you added.
   - Secrets and sensitive data: keys, tokens, passwords, connection strings,
     `.env` files, private keys, personal data in fixtures.
   - Stray artifacts: build output, coverage reports, editor files, large binaries.
5. **Stage explicit paths** (`git add <path> ...`). Avoid `git add -A` or
   `git add .` unless you have confirmed every file belongs. Run
   `git diff --staged --stat` and read it.
6. **Commit** with a message that follows the repository's convention (check
   `git log --oneline -20`): a concise imperative subject that says what changed,
   and a body explaining why when it is not obvious. Include any attribution the
   project or host requires.
7. **Deliver** as authorized and as the repository's branch policy says:
   - Push to the branch the project expects. Never force-push a shared branch
     without explicit approval.
   - When the project uses pull requests, push a branch and open one (for example
     `gh pr create`) with a summary, the checks run, and anything not verified.
   - If pushing fails (permissions, protected branch, failing hook), report the
     exact error. Do not bypass hooks or protections.

## Guardrails

- Do not commit, push, or open pull requests unless the user asked or the
  project's instructions explicitly direct it for this kind of change.
- Never rewrite published history, amend commits that are already pushed, or
  use `--no-verify`, unless the user explicitly asks.
- If a commit hook modifies files or fails, fix the cause and create a new commit;
  do not discard the hook's changes.
- Do not revert or delete files you did not create in this session.

## Verification

Success means every required check ran and passed, the staged diff contains only
intended files, and the commit or pull request exists where the project expects
it. Confirm with `git log --oneline -1`, `git status`, and, after pushing,
the remote branch or pull request URL.

## Report

- **Checks:** each command and its result (pass, fail, not run and why).
- **Diff audit:** files included, anything excluded and why, secret scan result.
- **Delivery:** commit hash and subject; branch pushed or pull request URL; or
  "not committed, awaiting approval".
- **Not verified:** environments, platforms, or slow suites not exercised.

## Optional delegation

The `verifier` subagent can check a change against acceptance criteria
independently. Re-run its key commands yourself before shipping.
