---
name: resolve-merge-conflicts
description: "Resolve Git merge, rebase, or cherry-pick conflicts by recovering what each side intended, combining compatible changes, regenerating lockfiles and generated files properly, and proving the result builds and passes tests. Use when a merge, rebase, or cherry-pick stops with conflicts. Not for reviewing the merged result for defects (use the review-change skill)."
---

# Resolve Merge Conflicts

Produce a resolution that keeps the intent of both sides, not just text that
compiles. Understand each change before choosing between them.

## When to use

- `git merge`, `git rebase`, `git cherry-pick`, or `git stash pop` reports conflicts.
- The user asks to bring a branch up to date with the default branch.

## When not to use

- Reviewing the merged code for bugs: use the `review-change` skill.
- Deciding whether to merge or rebase is a team policy question; follow
  `AGENTS.md` or ask.
- A broken rebase or reset, lost commits, or a bad pushed commit: use the
  `git-recovery` skill.

## Inputs to gather

- The operation in progress: `git status` shows "You have unmerged paths" plus
  "merging", "rebasing", or "cherry-picking".
- The unmerged files: `git diff --name-only --diff-filter=U` or `git ls-files -u`.
- The intent of each side: commit messages, linked issues, and pull request
  descriptions.

## Which side is "ours"

The labels flip between operations, and getting them backwards silently discards
work:

- **Merge** (`git merge feature` while on `main`): ours is `main` (HEAD), theirs is
  `feature`.
- **Rebase** (`git rebase main` while on `feature`): Git replays your commits on
  top of `main`, so **ours is `main`** (the base being rebuilt on) and **theirs is
  your commit** being replayed.
- **Cherry-pick**: ours is your current branch, theirs is the picked commit.

When in doubt, read the conflict marker labels and `git log -1 --format=%s MERGE_HEAD`
(merge) or `REBASE_HEAD` (rebase) to see which commit is incoming.

## Workflow

1. **Inspect each conflict with its base.** Show three versions:
   `git show :1:path` (common ancestor), `:2:path` (ours), `:3:path` (theirs).
   For a fuller picture, `git log --merge -p -- path` lists the commits on both
   sides that touched the file. Before you edit a file, you can re-render its
   markers with the base section included: `git checkout --conflict=zdiff3 -- path`
   (Git 2.35 or later; use `diff3` on older versions). This rewrites the file, so
   never run it after you have started resolving that file.
2. **State each side's intent** in a sentence ("ours renamed `getUser` to
   `fetchUser`; theirs added a `tenantId` parameter to `getUser`"). The correct
   resolution usually applies both: the renamed function with the new parameter.
3. **Resolve by kind:**
   - **Code:** combine the intents; update every call site affected by either
     side, including ones outside the conflict hunks.
   - **Imports and lists:** keep both entries, deduplicate, keep ordering rules.
   - **Lockfiles** (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`,
     `poetry.lock`, `Cargo.lock`): do not hand-merge. Resolve the manifest
     (`package.json`, `pyproject.toml`, `Cargo.toml`) first, take one side's
     lockfile (`git checkout --theirs -- <lockfile>` or `--ours`), then run the
     package manager's install or lock command so it re-resolves for the merged
     manifest.
   - **Generated files** (clients, snapshots, catalogs): resolve their sources,
     then regenerate with the project's command.
   - **Deleted versus modified:** decide whether the modification still matters
     after the deletion (move it to where the code now lives) or is obsolete.
4. **Remove every marker** and mark files resolved with `git add <path>`.
   Check with `git diff --check` (reports leftover conflict markers) and
   `git diff --name-only --diff-filter=U` (should print nothing).
5. **Check for semantic conflicts.** Code can merge cleanly and still break: one
   side renames a function while the other adds a new caller of the old name.
   Build, type-check, and run the tests before continuing.
6. **Continue the operation:** `git merge --continue`, `git rebase --continue`, or
   `git cherry-pick --continue`. During a rebase, repeat for each conflicting commit.

For conflicts that recur across a long rebase, `git rerere` can record and reuse
resolutions; enable it only if the user agrees (`git config rerere.enabled true`).

## Guardrails

- Never pick a whole side (`--ours` or `--theirs` for a source file) without
  understanding what the other side changed.
- Do not add unrelated fixes or formatting changes while resolving.
- Ask before aborting (`git merge --abort`, `git rebase --abort`): it discards the
  resolutions done so far. Never force-push a rewritten shared branch without
  explicit approval.
- If a conflict depends on a product decision (two incompatible behaviors), stop
  and ask rather than choosing silently.

## Verification

Run separately: `git diff --check`; the unmerged-files check above; the project's
build or type-check; and the test suites covering the conflicted files, then the
full suite.

## Report

- Operation and branches involved, with which side was ours and theirs.
- Each conflicted file: both intents and how they were combined.
- Lockfiles and generated files regenerated, with the commands used.
- Build and test results.
- Decisions that need the user's confirmation.
