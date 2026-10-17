---
name: git-recovery
description: "Diagnose and repair a bad Git state with the least destructive fix: commits on the wrong branch, a broken or abandoned rebase, merge, or reset, lost commits or stashes, a detached HEAD, an unwanted large file, or a bad commit or merge already pushed to a shared branch. Saves the current state first and gates every destructive command on approval. Use when history or the working tree is not what it should be. Not for resolving conflicts (use the resolve-merge-conflicts skill) or committed secrets (use the secret-leak-response skill)."
---

# Git Recovery

Get the repository to the state the user wants without losing anyone's work.
The stance is **inspect, save, then make the smallest fix**: nothing changes
until the current state is understood and backed up, shared history is fixed
with new commits rather than rewritten, and every command that can discard work
waits for explicit approval.

## When to use

- Commits landed on the wrong branch, often local `main` instead of a feature branch.
- A rebase, merge, cherry-pick, or reset went wrong or was left half-finished.
- Commits, a branch, or a stash seem lost, or work was committed on a detached HEAD.
- A large or unwanted file was committed (build output, a binary, a data dump).
- A bad commit or merge is already pushed to a shared branch.

## When not to use

- An operation stopped with conflicts that need resolving: use the
  `resolve-merge-conflicts` skill. Return here only if the result went wrong.
- A committed file holds a credential or other secret: use the
  `secret-leak-response` skill. Rotation comes before any history cleanup.
- Finished work needs checking, committing, and pushing: use the
  `verify-and-ship` skill.
- `git fsck` reports missing or corrupt objects: stop, copy the whole repository
  directory, and recover from a fresh clone or a collaborator's clone rather
  than running repair commands.

## Inputs to gather

Discover these first; ask only about what remains ambiguous.

- The end state the user wants, in one sentence, for example "these two commits
  on `feature/export`, and `main` matching `origin/main`".
- Whether the affected commits are pushed, and whether the branch is shared: the
  default branch, release and protected branches, and any branch someone else
  has pulled or built on. When unsure, treat it as shared.
- Team policy on rebasing, force pushes, and branch protection, from `AGENTS.md`,
  `CONTRIBUTING.md`, or the host settings.
- Uncommitted and untracked work in the tree, and whose it is.
- The Git version (`git --version`); `git switch` and `git restore` need 2.23 or later.

## Workflow

1. **Stop and inspect.** Run no state-changing command until you can explain
   how the repository got here. These are read-only:

   ```bash
   git status                              # branch, operation in progress, dirty files
   git log --oneline --graph --all -n 30   # recent commits across all refs
   git reflog -n 30                        # where HEAD has been, with SHAs
   git stash list
   git branch -vv                          # upstreams and ahead or behind counts
   git fetch origin                        # updates remote-tracking refs only
   git branch -r --contains SHA            # which remote branches hold this commit
   ```

2. **Classify the history.** Local-only commits (on no remote branch, or only on
   your own unshared branch) may be rewritten locally. Shared commits are fixed
   forward with new commits; rewriting them needs the team's agreement.
3. **Save the current state** before changing anything, and tell the user what
   each step does:
   - **Backup branch or tag at HEAD:** `git branch backup/TOPIC-DATE` (or
     `git tag`). It keeps the commits reachable whatever happens next, but it
     does not capture uncommitted changes. Record the SHA of every branch you
     will move (`git rev-parse main feature/export`).
   - **Dirty tree, stash:** `git stash push --include-untracked -m "before recovery"`
     saves staged, unstaged, and untracked changes, then removes them from the
     tree. Ignored files are not included (`--all` adds them). Restore later
     with `git stash apply`, which keeps the entry, rather than `pop`. Stashing
     fails while paths are unmerged.
   - **Dirty tree or operation in progress, copy:** copy the whole repository
     directory, including `.git`, to a location outside it. Only a copy captures
     everything: ignored files, half-finished rebase or merge state, hooks, and
     local configuration. Use it before complex recovery or when a stash is not
     possible.
4. **Choose the least destructive fix** from Fixes by situation. Prefer, in
   order: additive steps (a new branch, cherry-pick, revert); moving a local
   branch pointer (`git branch -f`, `git reset --soft`, `--mixed`, or `--keep`);
   and only then anything that discards.
5. **Get approval for each destructive command.** Show the exact command, what
   it discards (list below), and the backup that makes it recoverable. Wait for
   an explicit yes. Mark such commands `# requires approval` when you write them.
6. **Apply one step at a time and verify** (see Verification). Keep every
   backup until the user confirms the result.

### What destructive commands discard

- `git reset --hard REF`: all uncommitted changes to tracked files, staged or
  not. `git reset --keep REF` moves the branch the same way but refuses when it
  would overwrite local changes.
- `git clean -fd`: untracked files and directories. Git never stored them, so
  they cannot be recovered. Preview with `git clean -nd`; `-x` adds ignored files.
- `git checkout -- PATH` and `git restore PATH`: uncommitted changes in those paths.
- `git branch -D BRANCH`: an unmerged branch. Its own reflog is deleted with
  it; its commits survive only in the HEAD reflog, if they were ever checked out.
- `git stash drop` and `git stash clear`: stash entries, recoverable only as
  unreachable commits until garbage collection removes them.
- `git rebase --abort`, `git merge --abort`: conflict resolutions made so far.
- A force push: remote commits missing from your version, for everyone, and
  every collaborator's clone diverges.
- `git filter-repo` and other history rewrites: every later commit SHA, which
  breaks open pull requests, signatures, links, and existing clones.
- `git gc --prune=now`, `git prune`, `git reflog expire`: the unreachable
  objects recovery depends on. Never run these during recovery.

## Fixes by situation

**Commits on the wrong branch.** If local only, put them on the right branch and
move the wrong branch back (worked example below). If the right branch already
exists, `git switch` to it and `git cherry-pick BASE..WRONG` (a range, oldest
first) before moving the wrong branch back. If the commits are already on a
shared branch, revert them there and cherry-pick them onto the right branch.

**Operation left in progress.** `git status` names it. Either finish it (resolve
with the `resolve-merge-conflicts` skill, then `--continue`) or back out with
`git rebase --abort`, `git merge --abort`, or `git cherry-pick --abort`, which
return to the state before the operation. Aborting discards resolutions made so
far; ask first if there are any. `git rebase --quit` ends a rebase but leaves
HEAD where it is; check `git rebase --help` for your version.

**A finished rebase or reset went wrong.** The old tip is in the reflog:
`git reflog show BRANCH` lists earlier positions, and `ORIG_HEAD` holds the
pre-operation commit until the next reset, rebase, or merge. Create a branch at
the old tip first (`git branch recovered/TOPIC SHA`) and compare it with
`git diff OLD NEW` or commit by commit with `git range-diff OLD...NEW`. If the
branch is local, move it back with `git reset --keep SHA` on a clean tree. If
the bad result was already pushed, treat it as shared history.

**Uncommitted work lost to a reset or checkout.** Content that was staged
(`git add`) survives as dangling blobs: `git fsck --lost-found` writes each
one's content to a file under `.git/lost-found/other/`, without its file name;
read them to find the lost versions. Changes that were never staged were never
stored by Git; check the editor's local history.

**Lost commits or a deleted branch.** Look in `git reflog` (HEAD's history
outlives a deleted branch's own reflog), or in the message Git printed when the
branch was deleted (`Deleted branch NAME (was SHA)`). Then
`git branch NAME SHA`. If the reflog has nothing, `git fsck --lost-found` lists
dangling commits; identify them with `git show --stat SHA`. Reflogs are local to
each clone and expire (by default after 90 days, or 30 for entries no longer
reachable; see `gc.reflogExpire` in `git help config`), so recover promptly. A
pushed commit may still exist on the remote or in someone else's clone.

**Detached HEAD.** `git status` says `HEAD detached at ...`. To keep commits
made there, run `git switch -c NAME` before switching away. If you already left,
the reflog shows `checkout: moving from SHA to ...`; create a branch at that SHA.

**Missing stash.** A `git stash pop` that hits conflicts keeps the entry, so
check `git stash list` first. A dropped stash prints its SHA when dropped.
Otherwise search unreachable commits; stashes are merge commits whose subject
starts with `WIP on` or `On BRANCH:` (POSIX shell):

```bash
git fsck --unreachable --no-reflogs | grep commit | cut -d' ' -f3 \
  | xargs git log --merges --no-walk --format='%h %ci %s'
git stash apply SHA          # or keep it safe first: git branch recovered/stash SHA
```

**Large or unwanted file committed** (not a secret). In the last commit and not
pushed: `git rm --cached PATH`, add it to `.gitignore`, then
`git commit --amend`. In earlier unpushed commits: `git reset --soft BASE` keeps
every change staged so you can unstage the file and commit again; this squashes
those commits into one, so say so. A push rejected for file size leaves the
commit local, so the same fixes apply. Once pushed, remove the file in a new
commit; purging it from history is a rewrite that needs approval and
coordination. If the file must be versioned, propose Git LFS; it changes how
everyone clones, so ask.

**Bad commit or merge pushed to a shared branch.** Fix forward and push through
the team's normal flow; no force push is needed:

```bash
git revert SHA                       # a new commit that undoes one commit
git show --no-patch --format='%p' MERGE_SHA   # parents in order; parent 1 is normally the branch merged into
git revert -m 1 MERGE_SHA            # undo a merge, keeping parent 1's side
```

Reverting a merge undoes its changes but not its history: Git still considers
that branch merged. To merge the branch again later, first revert the revert
(`git revert REVERT_SHA`), then merge; otherwise the original changes stay
missing.

**Force push, only when approved.** Acceptable only on a branch nobody else
uses, or with the team's explicit agreement, and never on protected or default
branches without it. Name the remote SHA you expect to replace, so a commit you
have not seen is never overwritten; a bare `--force-with-lease` compares with
your remote-tracking ref, which a background fetch can silently update:

```bash
git push --force-with-lease=feature/export:EXPECTED_SHA origin feature/export   # requires approval
```

## Worked example: commits made on local main

Two commits meant for a feature branch were made on `main` and not pushed.
Illustrative; replace names to match the repository.

```bash
# Inspect: confirm the commits exist only locally.
git status                                    # On branch main, ahead of 'origin/main' by 2 commits
git fetch origin
git log --oneline origin/main..main           # the two commits to move
git branch -r --contains main                 # prints nothing: main's tip is on no remote branch

# Save: a backup branch costs nothing. Uncommitted changes stay in the tree.
git branch backup/main-before-move main

# Fix: a new branch keeps the commits, then local main moves back.
git switch -c feature/export                  # new branch at HEAD; uncommitted changes come along
git branch -f main origin/main                # moves only the main pointer; the working tree is untouched

# Verify.
git log --oneline origin/main..feature/export # the same two commits
git rev-parse main origin/main                # the same SHA twice
git diff backup/main-before-move feature/export   # empty: nothing was lost
```

If `git branch -r --contains main` lists `origin/main`, the commits are shared;
stop and use the bad-commit case instead. `git reset --hard origin/main` on
`main` would also move the pointer, but it discards uncommitted changes;
`git branch -f` from another branch moves only the pointer. To base the feature
branch on the latest `main`, rebase it now, while it is still local.

## Guardrails

- Inspect and back up before the first state-changing command, and check the
  result of each command before running the next.
- Run `git reset --hard`, `git clean -fd`, `git branch -D`, `git stash drop` or
  `clear`, a force push, or a history rewrite only after explicit approval of
  that exact command, shown with what it discards.
- Never run `git gc`, `git prune`, or `git reflog expire` during recovery.
- Fix shared branches with `git revert`. Never rewrite or force-push them
  without the team's agreement, and never change branch protection yourself.
- Revert or delete only what you created in this session, and say so. Never
  discard someone else's uncommitted work; stash or copy it first.
- Keep backup branches, tags, stashes, and copies until the user confirms the
  result; deleting them is the user's decision.
- If a secret is involved, stop and use the `secret-leak-response` skill before
  touching history. Never print the value.
- Do not push unless the user asked; delivery belongs to the `verify-and-ship` skill.

## Verification

Run each check separately and report the real output.

- `git status` shows the expected branch, no operation in progress, and only the
  expected uncommitted files.
- `git log --oneline --graph` for each affected branch matches the end state the
  user described.
- `git diff BACKUP RESULT` shows only intended differences; it is empty when
  commits were only moved.
- Recovered commits and stashes were inspected (`git show --stat SHA`) and match
  what the user expected.
- A revert inverts exactly the intended change (`git show REVERT_SHA`).
- The project's build and tests pass on the result, using the commands from
  `AGENTS.md`, package scripts, or the `Makefile`.
- After an approved push, `git ls-remote origin BRANCH` shows the expected SHA.

## Report

- **Starting state:** branches and SHAs, operation in progress, dirty files, and
  what was already pushed.
- **Diagnosis:** how it happened, with reflog evidence.
- **Backups:** branch and tag names with SHAs, stash entries, copy location.
- **Actions:** commands run in order, and the approval for each destructive one.
- **End state:** branches and SHAs, what was pushed, and what collaborators must
  do (for example re-sync after an approved force push).
- **Left for the user:** backups to delete once satisfied.
- **Not verified:** checks that could not run and why.

## Optional delegation

One agent can complete this workflow alone. The `verifier` subagent can run the
project's checks on the recovered branch, and the `reviewer` subagent can review
a revert or a reconstructed branch before it is pushed.
