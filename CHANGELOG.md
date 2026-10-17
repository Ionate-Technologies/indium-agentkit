# Changelog

All notable changes to this project are documented here.

## 2.0.0 - 2026-10-17

Every skill and subagent was rewritten to a lean, portable authoring standard,
and validation now enforces it.

### Breaking changes

- `frontend-builder` is now a write-scoped implementer with `Edit` and `Write`.
  The read-only frontend review role it used to hold is the new
  `frontend-reviewer` subagent. Update any automation that invoked
  `frontend-builder` expecting a review.
- `backend-builder` and `doc-writer` now declare `Edit` and `Write` and edit
  only the paths the parent assigns.
- `author-agentkit-content` is internal to this repository and no longer part of
  the `install` bundle. Install it explicitly with `add author-agentkit-content`.
- Skills no longer accept the JSON "context manifest" inputs the previous format
  described. Describe the task in plain language.

### Upgrading

Copies installed by 1.x are reported as "skipped" by a plain reinstall. Rerun
your install command with `--force` to replace them, for example
`npx @indium-ai-labs/agentkit install --target=claude --force`. Project context
files (`AGENTS.md`, `CLAUDE.md`) are never replaced.

The installer never deletes files, so a 1.x bundle install keeps its old copy of
`author-agentkit-content`, which the 2.0 bundle no longer manages. Delete that
directory from your agent's skills folder, or refresh it with
`add author-agentkit-content --force` if you contribute to agentkit.

### Added

- Skills: `upgrade-dependencies`, `address-review-feedback`, `init-agent-context`,
  `flaky-test-triage`, `query-optimization`, `build-llm-feature`,
  `mcp-server-development`, `secret-leak-response`, `containerize-service`, and
  `third-party-integration`.
- Subagents: `infrastructure-reviewer`, `frontend-reviewer`, `test-writer`,
  `debugger`, `plan-reviewer`, and `docs-researcher`.
- `--force` for `install.py` and the npm CLI.
- `templates/skill.md`, and validator rules for descriptions, size limits,
  cross-references, repository-only script references, destructive commands,
  subagent role and tool consistency, and inlined handoff headings.

### Changed

- Rewrote all skills and subagents to the standard in
  `skills/author-agentkit-content/SKILL.md`: trigger-focused descriptions, plain
  workflows, project-discovered commands, and a shared status and severity
  vocabulary for subagents. Total skill and subagent content shrank by about a
  fifth while the catalog grew from 73 to 89 items.
- `verify-and-ship` is now generic instead of running this repository's own
  pipeline in consumer projects.
- `.github/copilot-instructions.md` is now a compact skill index, and
  `ARCHITECTURE.md` shows the distribution pipeline and subagent roles.

### Fixed

- Removed rollback steps that discarded uncommitted work (`git checkout --`,
  `rm -rf` on variables, `prisma migrate reset`) or changed production without
  approval (automatic OTA rollbacks, `kubectl rollout undo`, flag flips).
- Removed `cmd1 || cmd2` fallback chains that could report success after a real
  test or lint failure, including in the `verifier` subagent.
- Removed references to scripts and templates that consumers never receive, and
  to subagents that did not exist.
- Corrected code examples that did not run, among them Python with `//` comments,
  a missing `self`, a nonexistent Playwright API, OpenAPI 3.1 `nullable`,
  deprecated Pact selectors and matcher arguments, a projection that dropped
  events, a CI aggregator that failed every fork pull request, and an A/B
  benchmark that measured the same build twice.

## 1.x

Changes released during the 1.x series, before this changelog recorded versions.

### Changed

- Refactored installation around explicit project/user scope, destination,
  target, and item selection so `add <name>` installs only the requested
  artifact and project installs never leak into user-level agent directories.
- Made npm installs durable copies by default, aligned project-context files
  with the selected agent architecture, and made target auto-detection fail
  closed when no agent directory exists.
- Consolidated validation and installer smoke tests into one cancellable CI
  workflow; the Windows smoke job now runs only for installer-related changes.

### Added

- Codex delegation guidance and a dependency-free delegation packet adapter.
- Deployment-safety, CI-pipeline, incident-triage, and infrastructure-review
  workflows.
- Release-engineer, CI-verifier, and incident-commander specialist agents.
- Frontend, backend API, and database-design implementation workflows.
- Specialist frontend-builder, backend-builder, and database-architect agents.
- Shared feature, API, migration, and verification handoff templates with
  structural validation.
- Per-item skill and subagent installation with installation diagnostics.
- Content scaffolding and catalog tooling.
- Planning, merge-conflict, migration, security-review, and release-note skills.
- Migration-planning, security-review, and performance-profiling subagents.
- Compatibility, security, and release guidance with installer smoke-test CI.
