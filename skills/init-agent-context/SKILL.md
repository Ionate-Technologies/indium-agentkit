---
name: init-agent-context
description: "Create or refresh a project's AGENTS.md, and CLAUDE.md for Claude Code, from repository evidence: what the project is, verified test and lint commands, source and test locations, conventions, and agent gotchas, kept short because it loads into every session. Use when a repository has no agent context file, the existing one is stale or wrong, or the user asks to set up agent instructions. Not for long human onboarding guides (use the onboard-to-codebase skill)."
---

# Init Agent Context

Write a short, accurate agent context file that every future session can trust.
The stance is **evidence over assumption**: every command in the file was run or
is marked unverified, and human-written rules already in place are kept.

## When to use

- The repository has no `AGENTS.md` or `CLAUDE.md`, or only a stub.
- Commands, layout, or conventions in the existing file are stale, wrong, or
  contradicted by CI.
- Agents keep making the same mistake in this repository, and the rule belongs in
  context.
- Several tool-specific instruction files should be consolidated into one source.

## When not to use

- A long-form guide for human newcomers (setup walkthrough, architecture tour,
  workflows): use the `onboard-to-codebase` skill, and link to its output from
  `AGENTS.md`.
- READMEs, API references, or architecture decision records: use the
  `write-documentation` skill.
- Mapping an unfamiliar repository without writing a file: delegate to the
  `explorer` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous.

- Existing context and convention files: `AGENTS.md` (root and nested),
  `CLAUDE.md`, `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`,
  `CONTRIBUTING.md`, `README`, and any development guide under `docs/`.
- Command sources: package scripts in `package.json`, `Makefile`, `justfile`,
  `Taskfile.yml`, `tox.ini`, `noxfile.py`, `pyproject.toml`, and CI workflows
  (`.github/workflows/`, `.gitlab-ci.yml`, and similar). CI shows which commands
  actually gate merges.
- Toolchain: language versions (`.nvmrc`, `.python-version`,
  `rust-toolchain.toml`, `go.mod`), the package manager (from the lockfile), and
  formatter, linter, and type-checker configs.
- Layout: source, test, generated, and vendored directories, and workspace
  definitions in a monorepo.
- Whether the user wants one source (`AGENTS.md`, with `CLAUDE.md` pointing to
  it) or separate files per tool.

## Workflow

1. **Read what exists.** Read every existing context file in full. Mark each
   human-written rule to preserve. Note contradictions, for example the README
   says `npm test` but CI runs `pnpm test:ci`. Generated files, such as rules built
   from another source, are not the source of truth; find and edit their source.
2. **Discover the project.** From manifests, the README, and entry points, write
   one to three sentences on what the project is, who uses it, and its main
   parts. Identify languages and frameworks with versions, source and test
   locations, generated or vendored paths agents must not edit by hand, and other
   important paths (configuration, migrations, API schemas).
3. **Discover commands.** Collect install, build, test (full suite and the
   single-test form), lint, format, and type-check commands. Prefer the form CI
   uses. Note required environment: services, Docker, and environment variable
   names (never their values).
4. **Run safe commands once.** Run tests, lint, format check, type check, and
   build where they are local and free of outside side effects. Record each
   command's result and roughly how long it took. Use the check form of
   formatters (for example `prettier --check`, `ruff format --check`) rather than
   the rewriting form. Never run deploy, release, publish, database migrations or
   seeds, or anything that needs production credentials; document those from
   their source and mark them unverified. If a command needs services or secrets
   you do not have, do not fake them; mark it unverified with the reason.
5. **Collect gotchas.** Look for what an agent would get wrong: a required
   codegen step, a non-default package manager, tests that need a running
   service, generated files, off-limits directories, commit or branch
   conventions, slow suites and how to run a subset. Sources: `CONTRIBUTING.md`,
   CI config, comments in config files, failures you hit in step 4, and the user.
6. **Draft the file** in the structure below. Keep it short, aiming under about
   100 lines, because it is loaded into every session and every line costs
   context. Prefer pointers ("Release steps: see `docs/releasing.md`") over
   copies. Write rules as direct instructions. Mark unverified commands inline,
   for example `(not verified: requires Postgres)`. Include no secret values,
   tokens, private hostnames, or personal data.
7. **Handle CLAUDE.md.** Claude Code reads `CLAUDE.md`. If the project wants one
   source, make `CLAUDE.md` a short file that imports the shared file with an
   `@AGENTS.md` line and adds only Claude-specific notes. Otherwise keep shared
   rules in `AGENTS.md` and only tool-specific rules in each tool's file. Do not
   copy the same rule into several files, where the copies will drift.
8. **Monorepos.** Keep the root file short and add package-level `AGENTS.md`
   files only where conventions differ. Many agent tools read the file nearest
   the code being edited; check what the project's tools support.
9. **Propose, then write.** If no context file exists, write the new file and
   show it. If one exists, show a diff of the proposed changes, justify each
   removal with evidence (for example "CI no longer runs this target"), and ask
   before overwriting. Never drop a human-written rule silently; if it looks
   obsolete, ask.

## Structure and example

The file mirrors the kit's template: three sections. Illustrative content for an
imagined project:

```markdown
# What this project is

Order-management API and admin UI for internal support staff. Python 3.12
FastAPI service in `api/`, React and Vite admin app in `web/`, Postgres 16.

# Conventions

- Language/framework: Python 3.12 (FastAPI, SQLAlchemy 2), TypeScript (React, Vite)
- Test command: `make test` (pytest in `api/`, `pnpm test` in `web/`; needs Docker for Postgres)
- Single test: `cd api && pytest tests/test_orders.py -k refund`
- Lint command: `make lint` (ruff, mypy, eslint)
- Source code lives in: `api/app/`, `web/src/`
- Tests live in: `api/tests/`, and `*.test.tsx` files next to components in `web/src/`
- Other important paths: Alembic migrations in `api/migrations/`; `web/src/api/schema.ts`
  is generated by `make codegen` and must not be edited by hand

# Notes for agents

- Use pnpm, not npm, in `web/`.
- Every model change needs a new Alembic migration; never edit an applied one.
- `make test` takes about 6 minutes; run the focused test first.
- Never run `make deploy` or anything under `ops/`; deploys go through CI.
- Release process: see `docs/releasing.md`.
- Not verified: `make e2e` (requires staging credentials).
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Preserve human-written rules. Propose changes to an existing context file as a
  diff and ask before overwriting or removing anything.
- Never run deploy, release, publish, migrate, seed, or cleanup commands to
  verify them.
- Never write secrets, credentials, or `.env` values into the file. It is
  committed to the repository and loaded into model context.
- Do not document a command you have neither run nor found in a script or CI
  config. A wrong command is worse than none.
- Never weaken or skip a check to make a documented command look green; record
  the real result.

## Verification

Run each command separately and report its real result; never chain
alternatives with `||`.

- Every command in the file either ran in this session with its result recorded,
  or is marked unverified with a reason.
- Every path in the file exists (check with `git ls-files` or the file tools).
- The diff contains no secret-shaped strings; run the project's secret scanner if
  it has one.
- Human-written rules from the previous version are present, or their removal was
  approved.
- The file is about 100 lines or fewer, or the extra length is justified.
- If the repository lints or validates its documentation, run that check.

## Report

- **Files:** created or changed, with line counts before and after.
- **Commands:** each documented command and its result (passed, failed, or
  unverified and why).
- **Preserved rules:** human-written rules kept, and any proposed for removal
  with the evidence.
- **Contradictions found:** between README, CI, and existing context files, and
  how each was resolved.
- **Gotchas added:** each new agent note and its source.
- **Not verified:** commands or paths that could not be checked and why.

## Optional delegation

The `explorer` subagent can map layout, entry points, and command sources while
you read the existing context files; run its commands yourself before
documenting them. One agent can complete this workflow alone.
