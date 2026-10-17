---
name: ci-pipeline
description: "Design or harden CI workflows, GitHub Actions by default, with fast merge-blocking checks, a correct required-checks aggregator, least-privilege tokens, SHA-pinned actions, safe caching, fork-safe triggers, timeouts, and concurrency. Use when creating or changing CI workflows, required checks, or branch protection proposals. Not for diagnosing a single failing run (delegate to the ci-verifier subagent) or flaky tests (use the flaky-test-triage skill)."
---

# CI Pipeline

Design or improve continuous integration so failures are actionable,
repeatable, and fast enough to run on every change. The stance is **every gate
maps to a real risk and runs a command developers can run locally**; security
defaults (read-only tokens, pinned actions, no untrusted code with secrets) are
not optional.

## When to use

- Creating a CI workflow, or changing its jobs, matrix, caching, permissions,
  triggers, artifacts, or required checks.
- Hardening an existing workflow against supply-chain or fork-based attacks.

## When not to use

- A specific CI run failed and needs diagnosis: delegate to the `ci-verifier`
  subagent, or use the `systematic-debugging` skill.
- A test passes and fails on the same code: use the `flaky-test-triage` skill.
- Deploying or promoting a release: use the `deployment-safety` skill.
- Writing or hardening the Dockerfile a job builds: use the
  `containerize-service` skill.
- Artifact signing, provenance, and dependency-confusion defenses: use the
  `supply-chain-security` skill.

## Inputs to gather

Discover these from the repository before asking.

- CI provider and existing workflows (`.github/workflows/`, `.gitlab-ci.yml`).
  Default to GitHub Actions only when no CI exists yet.
- Project commands for lint, typecheck, test, and build from `AGENTS.md`,
  `CLAUDE.md`, package scripts, or the `Makefile`. CI must call these, not
  inline its own logic.
- Supported runtimes from the project's policy (`engines`, `requires-python`,
  `.nvmrc`, `.tool-versions`). Never invent versions the project does not
  support.
- Platforms the project actually ships on; default to Linux only.
- Current branch protection or rulesets, merge queue use, and which check names
  are required today. Reading protection needs admin access; if denied, ask the
  user for the current settings.
- Which jobs need secrets or cloud access, and why.

## Workflow

1. **Map gates to risks.** List each existing and proposed check with the risk
   it guards (broken types, failing tests, vulnerable dependencies, a broken
   build). A check with no risk is noise; a risk with no check is a gap.
2. **Separate fast from slow.** Merge-blocking fast jobs (lint, typecheck, unit
   tests) should finish within the team's target, for example under 10 minutes.
   Integration, browser, security, and packaging jobs run in parallel or after
   them with explicit `needs:`.
3. **Add one aggregator job** that is the only required check. It runs with
   `if: always()` and fails on any `failure` or `cancelled` result. Jobs that
   must always run must report `success`; a job skipped by design (for example
   integration on fork pull requests) may report `skipped`, but only in the
   situation where the skip is expected. Use `always()` rather than
   `!cancelled()`: a skipped aggregator counts as passing.
4. **Keep the matrix minimal.** Oldest and newest supported runtime, only the
   shipped platforms, `fail-fast: false` so one leg does not hide the others.
5. **Least privilege.** Set top-level `permissions:` to `contents: read` (or
   `{}` with per-job grants), and escalate per job with a comment explaining why.
   Test-only jobs never hold `contents: write`, `id-token: write`, cloud roles,
   or deployment credentials. Deploys go through protected environments.
6. **Pin actions to full commit SHAs** with a trailing version comment. Resolve
   the current release yourself; never copy a SHA from an example or from
   memory (see "Resolving action SHAs" below). Let Dependabot or Renovate keep
   the pins and comments current.
7. **Fork safety.** Run untrusted pull-request code only under `pull_request`,
   which gives forks a read-only token and no secrets. Never use
   `pull_request_target` (or `workflow_run`) to check out and run the pull
   request's head code. Pass PR titles, branch names, and comment bodies to
   scripts through `env:`; never interpolate them with `${{ }}` directly inside
   `run:`. Use `persist-credentials: false` on checkout.
8. **Cache inside trust boundaries.** Key caches on the lockfile hash and
   runtime version. Do not restore dependency caches in release or publish
   jobs that hold signing or publishing credentials; install cleanly there.
   Content written by an untrusted ref must never reach a privileged job.
9. **Make runs deterministic and bounded.** `timeout-minutes` on every job (the
   provider default is hours). A `concurrency` group per workflow and ref that
   cancels superseded pull-request runs but lets pushes to the default branch
   finish. Upload test reports and diagnostics under `if: failure()` with
   per-leg artifact names and short `retention-days`.
10. **Check the trigger wiring.** If the repository uses a merge queue, add the
    `merge_group` trigger, or required checks never report there. Do not put
    `paths` or `paths-ignore` on a workflow that produces a required check: when
    it does not run, the check stays pending and blocks merging.
11. **Propose, do not apply, protection changes.** Branch protection and
    ruleset changes are outward-facing; present them as a proposal and apply
    only with explicit approval (see below). Then run the Verification checks.

## Reference: hardened GitHub Actions workflow

Illustrative. Replace every `<commit-sha> # vX.Y.Z` with a resolved pin and the
`npm run` scripts with the project's own commands.

```yaml
name: ci

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

# Cancel superseded pull-request runs; let every push to main finish.
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

# Read-only token by default. Jobs escalate only with a stated reason.
permissions:
  contents: read

jobs:
  static:
    name: Lint and typecheck
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          persist-credentials: false
      - uses: actions/setup-node@<commit-sha> # vX.Y.Z
        with:
          node-version-file: .nvmrc
          cache: npm
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck

  unit:
    name: Unit (Node ${{ matrix.node }})
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        node: ["22", "24"] # oldest and newest versions the project supports
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          persist-credentials: false
      - uses: actions/setup-node@<commit-sha> # vX.Y.Z
        with:
          node-version: ${{ matrix.node }}
          cache: npm
      - run: npm ci
      - run: npm test # project script, configured to write JUnit XML to reports/
      - if: failure()
        uses: actions/upload-artifact@<commit-sha> # vX.Y.Z
        with:
          name: unit-report-node${{ matrix.node }}
          path: reports/
          retention-days: 7

  integration:
    name: Integration
    needs: [static, unit]
    # Fork pull requests get no secrets, so this job is skipped for them by design.
    if: >-
      github.event_name != 'pull_request' ||
      github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          persist-credentials: false
      - uses: actions/setup-node@<commit-sha> # vX.Y.Z
        with:
          node-version-file: .nvmrc
          cache: npm
      - run: npm ci
      - run: npm run test:integration
        env:
          SERVICE_TOKEN: ${{ secrets.INTEGRATION_SERVICE_TOKEN }}

  build:
    name: Build
    needs: [static]
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@<commit-sha> # vX.Y.Z
        with:
          persist-credentials: false
      - uses: actions/setup-node@<commit-sha> # vX.Y.Z
        with:
          node-version-file: .nvmrc
          cache: npm
      - run: npm ci
      - run: npm run build

  all-checks:
    name: Required checks
    needs: [static, unit, integration, build]
    # always(), not !cancelled(): a skipped aggregator would count as passing.
    if: always()
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      # Fail on any failure or cancellation, on a skip of an always-run job,
      # and on an integration skip outside fork pull requests.
      - name: Fail unless required jobs passed
        if: >-
          contains(needs.*.result, 'failure') ||
          contains(needs.*.result, 'cancelled') ||
          needs.static.result != 'success' ||
          needs.unit.result != 'success' ||
          needs.build.result != 'success' ||
          (needs.integration.result == 'skipped' && (github.event_name != 'pull_request' ||
          github.event.pull_request.head.repo.full_name == github.repository))
        run: exit 1
```

Require only `Required checks` in branch protection. Individual jobs then can
be renamed or split without silently dropping a gate, and a job skipped by
design does not need special handling in protection settings.

### Resolving action SHAs

Find the latest release, then resolve its tag to a commit:

```bash
gh release view --repo actions/checkout --json tagName --jq .tagName
gh api repos/actions/checkout/git/ref/tags/v4.2.2 --jq '.object.type + " " + .object.sha'  # use the tag printed above
# If the type is "tag" (an annotated tag), dereference that object to the commit:
gh api "repos/actions/checkout/git/tags/$TAG_OBJECT_SHA" --jq .object.sha
```

The release page on GitHub shows the same commit. Pin the commit SHA and keep
the tag as a trailing comment.

### Branch protection proposal

Present this to the user; do not apply it unasked. The `PUT` endpoint replaces
the whole protection configuration, so start from the current settings
(`gh api repos/{owner}/{repo}/branches/main/protection`) and change only the
required checks. `enforce_admins`, `required_pull_request_reviews`, and
`restrictions` are required keys: copy their current values, not the example
values, converting from the read shape where it differs (for example
`enforce_admins.enabled` becomes a plain boolean). If the repository uses
rulesets (`gh api repos/{owner}/{repo}/rulesets`), propose the change to the
ruleset instead.

```json
{
  "required_status_checks": { "strict": true, "checks": [{ "context": "Required checks" }] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 1, "dismiss_stale_reviews": true },
  "restrictions": null
}
```

```bash
gh api --method PUT repos/{owner}/{repo}/branches/main/protection --input protection.json  # requires approval
```

## Guardrails

- Revert or delete only files you created or changed in this session. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Branch protection, rulesets, repository settings, secrets, and environments
  are outward-facing.
- Never weaken a required check, skip a failing test, lower a coverage
  threshold, add `continue-on-error` to a gate, or bypass protection to get a
  green build. Fix the cause or report it with evidence.
- Never print secrets, write them to step outputs or artifacts, or grant write
  or cloud permissions to test-only jobs.
- Never run untrusted pull-request code in a job that holds secrets or a write
  token.
- Every command CI runs must exist as a project-local command developers can
  run themselves.

## Verification

Use the project's own commands, each run separately, and report the real result.

1. `actionlint` (from the repository root) passes on every changed workflow.
2. `zizmor .github/workflows/` reports no new findings at medium or above, or
   each remaining one is explained. Some audits need a GitHub token or network
   access; check `zizmor --help` for offline mode.
3. Each fast-job command passes locally on a clean checkout (for example
   `npm ci`, then `npm run lint`, `npm run typecheck`, `npm test`).
4. If `act` is installed, `act -n` catches wiring errors; it does not reproduce
   hosted runners exactly.
5. After the workflow runs on a branch, confirm the aggregator's check name
   matches what branch protection requires. Confirm a fork pull request passes
   the aggregator with integration skipped; if none is available, walk through
   the conditions for each trigger and report it as not run.

## Report

- **Workflows changed:** files, triggers, and jobs added, removed, or renamed.
- **Gates:** each required check and the risk it guards; what is now
  merge-blocking versus advisory.
- **Permissions:** the top-level set and every per-job escalation with its reason.
- **Pins and caches:** actions pinned (with versions), cache keys, and trust
  boundaries.
- **Protection proposal:** the exact change proposed and whether the user
  approved and applied it.
- **Verification:** each command and its result.
- **Not verified:** provider behavior that only a real run shows, expected job
  durations, and known flaky checks with tracking issues.

## Optional delegation

The `ci-verifier` subagent can diagnose a failing or skipped check in parallel.
The `infrastructure-reviewer` subagent can review deployment workflows and the
infrastructure they touch. The workflow above stays complete for one agent.
