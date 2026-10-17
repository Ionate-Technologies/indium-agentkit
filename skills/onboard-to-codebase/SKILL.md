---
name: onboard-to-codebase
description: "Produce a verified onboarding guide for a repository covering purpose, prerequisites, setup, source layout, key abstractions, common workflows, and gotchas, with every setup and test command run or marked unverified. Use when new contributors need a persistent guide to get from clone to a passing test run and their first change. Not for quick orientation before a change (delegate to the explorer subagent) or AGENTS.md and CLAUDE.md files (use the init-agent-context skill)."
---

# Onboard to Codebase

Write a guide a new contributor can follow today, from clone to a green test
run to a first change. The stance is **run it or mark it**: every setup, build,
and test command in the guide was executed here and recorded, or is labeled
unverified with the reason.

## When to use

- Someone asks for an onboarding guide, contributor setup doc, or "how this repo
  works" overview that will be saved and maintained.
- The README lacks working setup steps and new people keep hitting the same
  problems.

## When not to use

- Your own quick orientation before a change: delegate to the `explorer`
  subagent, which returns a structural map without writing a document.
- READMEs, API references, how-to guides, or ADRs: use the
  `write-documentation` skill.
- `AGENTS.md`, `CLAUDE.md`, or other agent context files: use the
  `init-agent-context` skill.
- Operational procedures for production: use the `write-runbook` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Audience:** the roles the guide serves (frontend, backend, operations) and
  the operating systems contributors use.
- **Existing docs:** `README.md`, `CONTRIBUTING.md`, `docs/`, ADRs, `AGENTS.md`
  or `CLAUDE.md`, and where onboarding docs belong (for example
  `docs/onboarding.md`).
- **Manifests and lockfiles:** `package.json` with its lockfile (the lockfile
  shows the package manager), `pyproject.toml`, `go.mod`, `Cargo.toml`,
  `Gemfile`, `pom.xml` or `build.gradle`, and workspace or monorepo config.
- **Version pins:** `.nvmrc`, `.node-version`, `.tool-versions`,
  `.python-version`, `rust-toolchain.toml`, the `engines` and `packageManager`
  fields, and devcontainer or Nix files.
- **Task runners and services:** `Makefile`, `justfile`, `Taskfile.yml`, package
  scripts, `compose.yaml` or `docker-compose.yml`, and `.env.example`.
- **CI configuration:** the most reliable record of the real setup steps.
- **Access needs:** accounts, secrets, VPN, or cloud permissions a contributor
  must request. Ask the user; never copy secret values into the guide.

## Workflow

1. **Read the existing docs first.** Note what they cover, what is missing, and
   what looks stale. The guide complements them: link to the README and
   CONTRIBUTING for anything they already cover correctly.
2. **Map the repository.** List top-level directories with one line each, the
   entry points (server bootstrap, CLI main, app root, route definitions), the
   packages in a monorepo, and where tests live. Recent activity shows where
   newcomers will work; this read-only command lists the most-changed files:

   ```bash
   git log --since="6 months ago" --name-only --format="" | grep -v '^$' | sort | uniq -c | sort -rn | head -20
   ```

3. **Derive setup from evidence,** preferring CI steps, manifests, and version
   files over prose. Order it as prerequisites with versions, clone, install
   with the lockfile respected (for example `npm ci`,
   `pnpm install --frozen-lockfile`, `uv sync`, `poetry install`), environment
   variables (each required one, what it does, and where to get its value),
   local services, local migrations and seed data, the dev server, and tests.
4. **Verify each command where it is safe.** Run it here and record the result
   and any fix you needed; every fix is a gotcha for the guide. Ask before long
   installs, large container pulls, or anything that writes outside the
   repository. Do not run commands that touch shared or production resources,
   need real credentials, or cost money; mark them unverified with the reason.
   Run migrations and seeds only against a local, disposable database.
5. **Name the key abstractions,** the five to ten concepts a newcomer meets
   first (domain models, request lifecycle, dependency injection, state stores,
   plugin or module system, background jobs). For each, give the defining file
   as `path:line` and one sentence on its role. Do not list every file.
6. **Write the common workflows** with the project's real commands: adding a
   feature (where code and tests go, conventions to follow), fixing a bug, running
   focused tests, lint and format, database migrations, and how releases and
   deploys happen. Link to runbooks for deploys; do not run them. Focused-test
   forms differ by tool, for example `npx vitest run path/to/file.test.ts -t "name"`,
   `pytest tests/test_orders.py -k name`, `go test ./orders -run TestName`, or
   `cargo test name`; use the one the project's scripts support.
7. **Collect gotchas** from failures during verification, CI-only steps,
   required variables without defaults, generated code that must be
   regenerated, platform differences (line endings, case-sensitive paths, file
   watchers), and slow or flaky steps.
8. **Save the guide** where the project keeps such docs, for example
   `docs/onboarding.md`, and suggest a one-line link from the README. Do not
   overwrite `README.md` or `CONTRIBUTING.md`; propose a minimal patch and ask
   before editing them.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
- Never weaken a test, check, or threshold to make work pass, including to make
  a setup step look green.
- Describe the code as it is. Label planned or aspirational architecture as
  planned, or leave it out.
- Never put secret values, internal hostnames the user has not cleared, or
  personal data into the guide; describe where to obtain them instead.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Each setup, build, and test command in the guide is marked verified (with
  its result) or unverified (with the reason).
- Every `path:line` and directory named in the guide exists at the recorded
  commit.
- Relative links in the guide resolve, and the project's markdown lint passes
  if configured.

## Report

Return a short summary (guide location, commit, commands verified and
unverified, docs gaps noticed) and the guide in this structure:

<!-- handoff: onboarding-guide -->
```markdown
# Onboarding guide

## Project overview

Purpose, users, and high-level architecture, in a few sentences.

## Prerequisites

Tools, runtimes, and accounts, with versions and how to get access.

## Development setup

Numbered steps from clone to a running app and a passing test run. Each
command marked verified or unverified.

## Source layout

Top-level directories and entry points, one line each.

## Key abstractions

Five to ten core concepts, each with its defining `path:line`.

## Common workflows

### Adding a feature

### Fixing a bug

### Running tests

### Deploying

## Gotchas and tips

Known pain points, required variables, CI-only steps, and platform differences.

## Handoff

**Changed contract:** none, or the docs added or changed.

**Files / systems affected:** the guide's path and any linked docs.

**Evidence and tests:** commands run and their results.

**Risks / rollback:** unverified steps and areas likely to go stale.

**What the next agent needs:** open questions, access requests, and doc gaps.
```

## Optional delegation

The `explorer` subagent can map the layout, entry points, and data flows
read-only while you verify setup commands. The `doc-writer` subagent can draft
sections into the assigned guide path. Re-check any `path:line` or command a
subagent reports before it goes into the guide.
