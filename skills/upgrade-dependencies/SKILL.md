---
name: upgrade-dependencies
description: "Upgrade a framework, runtime, or library across a major version (for example React 18 to 19, a Node.js LTS bump, a Django or Spring Boot major, a new Python minor) by reading every intermediate migration guide, upgrading in small verified increments, applying vendor codemods, and recording behavior changes. Use when asked to upgrade, bump, or migrate to a newer major version. Not for deciding what is vulnerable or stale (use the dependency-audit skill)."
---

# Upgrade Dependencies

Move a project to a newer major version of a framework, runtime, or library
without surprise breakage. The stance is **read every migration note, then move
one verified step at a time**: no version jump without its changelog read, and no
increment is done until the full verification passes.

## When to use

- A framework or library major upgrade: React, Angular, Next.js, Django,
  Spring Boot, Rails, and similar.
- A runtime bump: a new Node.js LTS, a Python minor version, a JDK release, a Go
  or Rust toolchain change.
- A security fix that ships only on a newer major line.
- Peer-dependency pressure: one package cannot move until another does.

## When not to use

- Deciding what is vulnerable, stale, unused, or license-risky: use the
  `dependency-audit` skill, then return here for the upgrades it recommends.
- The upgrade changes a stored data, schema, or wire format that existing data or
  clients depend on: plan that part with the `safe-migration` skill.
- A large mechanical source rewrite with no vendor codemod: use the
  `ast-manipulation-codemods` skill to write one.
- A test fails after an upgrade and the cause is unclear: use the
  `systematic-debugging` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- Current versions, declared and resolved: the manifest and lockfile
  (`package.json` with its lockfile, `pyproject.toml`, `requirements*.txt`,
  `pom.xml`, `build.gradle`, `go.mod`, `Cargo.toml`, `Gemfile.lock`) and the
  installed version (for example `npm ls react`, `pnpm why react`,
  `pip show django`, `mvn dependency:tree`, `go list -m all`).
- Why the upgrade is wanted: a security fix, end of support, a needed feature, or
  a peer constraint. This sets the target and how far to go.
- The target: the latest release, or a specific line such as an LTS.
- Runtime declarations: `engines` in `package.json`, `.nvmrc` or `.node-version`,
  `requires-python`, `.python-version`, Docker base images, CI matrices, and
  deployment platform settings.
- The package manager (from the lockfile) and the test, lint, type-check, and
  build commands from `AGENTS.md`, `CLAUDE.md`, package scripts, or the `Makefile`.
- Whether the user wants commits, and on which branch.

## Workflow

1. **Baseline.** Record the current versions of the target and its companions
   (for example `react`, `react-dom`, `@types/react`, testing libraries). Run the
   full verification on the untouched tree and record the result. If the baseline
   already fails, report it and ask whether to proceed; otherwise you cannot tell
   upgrade breakage from existing breakage.
2. **Read every migration note between current and target.** Read the official
   changelog, release notes, and upgrade or migration guide for each release line
   in between. Do not skip intermediate versions: an API deprecated in version N
   is often what breaks in N+1. For frameworks with a fixed deprecation timeline,
   such as Django, that means every feature release. Use the docs for the exact
   versions, not memory or a blog post. List each breaking change, search the
   codebase for the affected API, and mark it as applies, does not apply, or
   unsure.
3. **Check constraints.** Check peer-dependency ranges, plugins and adapters that
   must move together, transitive dependencies pinned to the old line
   (`npm ls`, `pnpm why`, `pipdeptree` if installed, `mvn dependency:tree`,
   `cargo tree`), and runtime minimums (for example Spring Boot 3 requires Java 17
   or later and moves from `javax.*` to `jakarta.*` packages). For a Python or
   Node.js bump, check that compiled or native dependencies publish builds for the
   new version. If a required companion has no compatible release, stop and report
   the blocker with options (wait, replace, fork, or stay) instead of forcing it.
4. **Plan the smallest increments.** One major at a time when possible. Upgrade
   test tooling first if the current version cannot run against the target. Move
   to the latest minor of the current major first when it adds warnings for the
   next major. Each increment is one coherent change that passes verification on
   its own. Share the plan before starting when it has more than a couple of
   increments or touches the runtime.
5. **Apply one increment.**
   - Change only the packages in this increment, with the project's package
     manager (for example `npm install react@19 react-dom@19`, `pnpm add`,
     `poetry add`, `uv add`, or editing `pom.xml` or `build.gradle`).
   - Let the package manager update the lockfile for those packages. Do not
     delete and regenerate the whole lockfile; that silently upgrades every
     transitive dependency. Commit the lockfile with the manifest.
   - Run the codemods the vendor or project provides, or established community
     ones, for example the ones named in the React upgrade guide, `@next/codemod`, `ng update`, `django-upgrade`,
     `pyupgrade`, or OpenRewrite recipes for Spring. Check each tool's docs for
     the exact invocation for your versions. Review codemod output like any other
     diff. If no codemod exists and the change is large and mechanical, use the
     `ast-manipulation-codemods` skill.
   - Fix the remaining breaking changes by hand from the list in step 2.
6. **Fix deprecations.** Run tests with deprecation warnings visible, for example
   `python -W error::DeprecationWarning -m pytest`, Django's
   `python -Wa manage.py test`, or `node --trace-deprecation`. Fix the warnings
   the next increment will turn into errors; list the rest as follow-ups.
7. **Verify the increment** (see Verification). If it fails, fix the cause; do not
   skip, quarantine, or loosen tests. If an increment cannot be made green, stop,
   report what blocks it, and leave the tree at the last green increment,
   reverting only your own changes.
8. **Commit per increment** when the user wants commits: one reviewable commit
   per increment, with a subject naming the versions (for example
   `Upgrade React to 19`). Put large codemod output in its own commit so
   reviewers can separate mechanical changes from manual ones.
9. **Record runtime behavior changes** that users or operators could notice:
   changed defaults, removed configuration, new runtime minimums, different
   serialization, error messages, or performance. These go in the report and in
   the changelog or release notes if the project keeps them.
10. **Repeat** steps 5 to 9 for each increment, then report.

## Worked example: increment plan

Illustrative, for React 18.2 to 19 in a TypeScript app. React 18.3 exists to add
warnings for APIs that 19 removes; check the current React 19 upgrade guide for
the real breaking-change list and codemod commands.

```markdown
| Step | Change                                                  | Gate                                  |
|------|---------------------------------------------------------|---------------------------------------|
| 0    | Baseline on React 18.2                                  | Suite, type check, build green        |
| 1    | Test libraries to versions that support both 18 and 19  | Suite green, still on React 18        |
| 2    | react and react-dom to 18.3; fix the new warnings       | Suite green, warnings fixed or listed |
| 3    | Codemods named in the upgrade guide                     | Codemod diff reviewed, suite green    |
| 4    | react, react-dom, @types/react, @types/react-dom to 19, | Suite, type check, build green;       |
|      | plus manual fixes from the breaking-change list         | behavior changes recorded             |
```

Each row is its own commit. A failure at step 4 is investigated at step 4, not
after more changes are stacked on top.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never upgrade unrelated packages in the same change. List other stale packages
  you notice as follow-ups.
- Never silently bypass dependency resolution: `npm install --force`,
  `--legacy-peer-deps`, new `overrides` or `resolutions` entries, or pip
  `--no-deps`. Explain the conflict and ask. If the user approves, record the
  override and its reason in the report.
- Ask before changing runtime or engine requirements that affect deployment or
  consumers: `engines`, `.nvmrc`, `requires-python`, Docker base images, CI
  matrices, or minimum supported platform versions. The deployment environment
  has to change with them.
- For a library others consume, a raised peer or runtime minimum is a breaking
  change for them; say so in the report.
- Never weaken a test, check, type rule, or lint rule to make an upgrade pass, and
  never add blanket warning filters to hide deprecations.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- A clean install from the lockfile succeeds with the project's frozen-install
  command (for example `npm ci`, `pnpm install --frozen-lockfile`,
  `uv sync --locked`).
- The resolved versions are the intended ones, and only one copy is installed of
  packages that break when duplicated (React is one).
- Type check, lint, the full test suite, and the production build pass.
- Deprecation warnings that the next major turns into errors are fixed or listed.
- If the app runs locally, start it and exercise a primary flow; upgrades often
  break what tests do not cover (routing, hydration, configuration loading).
- `git diff` contains only the planned packages, the lockfile, codemod output, and
  the fixes.

## Report

- **Versions:** before and after for each package and runtime changed.
- **Why:** the reason for the upgrade and the target chosen.
- **Breaking changes handled:** each relevant migration-guide item and how it was
  addressed, plus items confirmed not to apply.
- **Codemods run:** command, tool version, and files changed.
- **Overrides and runtime changes:** any approved override or engine change, with
  the reason.
- **Verification:** each command and its result, per increment.
- **Behavior changes:** runtime differences users or operators may notice.
- **Follow-ups:** remaining deprecations, blocked companions, unrelated stale
  packages.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `docs-researcher` subagent can collect version-exact changelogs and migration
guides for each increment while you inventory the codebase. The
`dependency-auditor` subagent can map peer and transitive constraints, or confirm
that the upgrade resolved the advisories that motivated it. The `reviewer`
subagent can review each increment's diff. One agent can complete this workflow
alone.
