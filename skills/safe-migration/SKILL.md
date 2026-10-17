---
name: safe-migration
description: "Plan and run a staged migration of a database schema, API contract, configuration, storage engine, or file format using expand-migrate-contract, with reconciliation evidence per stage and approval-gated rollback. Use when changing something that existing data, deployed versions, or consumers depend on, such as renaming or splitting columns, versioning an endpoint, renaming config keys, or moving storage. Not for designing a new schema (use the database-design skill)."
---

# Safe Migration

Move data, traffic, or consumers from an old representation to a new one
without downtime, data loss, or broken consumers. The default approach is
**expand-migrate-contract**: add the new path beside the old one, move data and
traffic through verifiable stages, and remove the old path only after the new
one is proven. The stance is **evidence per stage, approval before anything
irreversible**: every stage ends in recorded checks, and the agent never runs a
data or traffic rollback, or an irreversible step, without explicit approval.

## When to use

- Renaming, splitting, retyping, or moving columns or tables that hold live data.
- Versioning, changing, or removing API fields or endpoints that deployed
  clients use.
- Renaming configuration keys, flags, or environment variables; switching
  storage engines or buckets; changing a serialization or file format.

## When not to use

- Designing a new schema, constraints, or indexes: use the `database-design`
  skill. It produces the DDL and plan that this skill executes.
- Rolling out an ordinary release with no data or contract change: use the
  `deployment-safety` skill.
- Upgrading library versions: use the `upgrade-dependencies` skill.
- Independent review of the plan: delegate to the `migration-planner` subagent.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous.

- Source and target state, precise enough to diff (DDL, API contract, key set,
  or format specification). If either is ambiguous, ask before planning.
- Producers and consumers of the affected artifact, found by searching the
  repository for the table, endpoint, key, or format module. Record the search;
  never assume an empty consumer list.
- Version overlap: one atomic deploy, a rolling deploy where old and new
  versions coexist, or long-lived clients (mobile apps, external API clients,
  partner integrations).
- Migration tooling, deployment pipeline, feature-flag system, backup and
  restore capability, and who approves production steps.
- Data volume and write rate, for batching and lock assessment.

## Workflow

1. **Inventory consumers** and classify each by update latency: deploys with
   the server, rolls independently, or long-lived and pinned.
2. **Write the overlap contract:** which versions read and write which
   representation at each stage. At every moment, everything any deployed writer
   emits must be readable by every deployed reader.
3. **Define preflight checks and a measurable cutover criterion**, for example
   zero reconciliation mismatches over an observation window agreed with the
   owner, and consumer error rates flat. Reject criteria such as "looks fine".
4. **Decompose into stages** (see the table below). If the change truly cannot
   be decomposed, write down why, shrink its blast radius, and treat it as one
   gated irreversible stage.
5. **Design the rollback for every stage before running any stage.** Rehearse
   it on a disposable or staging copy; an untested rollback is a hypothesis.
   Mark any stage without a rollback as irreversible.
6. **Implement the smallest verifiable stage.** Copy rather than rewrite in
   place, rename before dropping, and keep unrelated refactors out of the
   migration diff. Deploy dual writes before the backfill so rows written during
   the backfill are covered. Backfills run in bounded, resumable, idempotent
   batches keyed by primary key.
7. **Run preflight, then one stage per rollout window.** Ask before running any
   stage against a shared or production environment. Watch error rate, latency,
   replication lag, and consumer health before advancing.
8. **On a regression, halt and report.** Pausing a job this session started is
   always allowed. Propose the stage's rollback with the evidence, and run it
   only after explicit approval.
9. **Reconcile and decide cutover** against the criterion with recorded
   evidence. If it is not met, extend the observation window or propose rollback.
10. **Contract and clean up** as separate, individually approved changes, each
    with its own rollback note.

## Stages by migration kind

| Kind | Expand | Migrate | Contract |
| --- | --- | --- | --- |
| Schema | Add the new column or table, nullable | Dual write, backfill, compare reads | Stop old writes, then drop after a quiet period |
| API | Add the new field or version beside the old | Move clients; measure old-path usage per client | Announce deprecation (for example a `Sunset` header), remove at zero usage |
| Config | Read the new key, fall back to the old | Set the new key everywhere; log fallback hits | Remove the fallback, then the old key |
| Format or storage | Readers accept old and new | Switch writers after every reader ships; copy stored data | Drop the old reader when no old data remains |

## Reference example: plan for splitting a column

Illustrative. Every rollback that reverses data or traffic is approval-gated.

```yaml
migration: split-users-full-name
kind: schema
source_state: users.full_name text NOT NULL, read and written by every version
target_state: users.first_name and users.last_name text NOT NULL; full_name removed
version_overlap: rolling_deploy
producers:
  - "api-server: POST /users, PATCH /users/:id"
  - admin-import-job
consumers:
  - "api-server: GET /users/:id"
  - billing-sync-worker
  - email-service

preflight:
  - Restorable backup of users verified, with a recent restore drill.
  - Replication lag within the project's limit on every replica.
  - api-server can be rolled back through the deploy pipeline.

stages:
  - name: expand
    change: ALTER TABLE users ADD COLUMN first_name text, ADD COLUMN last_name text;
    verify: Columns exist and are nullable; canary deploy healthy.
    rollback: ALTER TABLE users DROP COLUMN first_name, DROP COLUMN last_name;  # requires approval
  - name: dual_write
    change: Writers set full_name and the split columns through one shared split function.
    verify: Every new row has both representations; write error rate flat.
    rollback: Turn off the dual_write flag; full_name stays authoritative.  # requires approval
  - name: backfill
    change: Batches of 1000 rows by primary-key cursor WHERE first_name IS NULL, throttled and resumable.
    verify: Reconciliation queries 1 and 2 return zero rows or zero counts.
    rollback: Pause the job (allowed without approval); written values are additive and unread.
  - name: dual_read
    change: Readers compare both representations and log mismatches; responses still use full_name.
    verify: Mismatch rate stays zero for the agreed window (for example 7 days).
    rollback: Turn off comparison logging.  # requires approval
  - name: cutover
    change: Flag reads to first_name and last_name.
    criterion: Zero mismatches for the window, and smoke checks pass for every consumer.
    rollback: Flag reads back to full_name; no data moves.  # requires approval
  - name: enforce
    change: For each split column, add CHECK (col IS NOT NULL) NOT VALID, VALIDATE it, then SET NOT NULL.
    rollback: ALTER TABLE users ALTER COLUMN first_name DROP NOT NULL, ALTER COLUMN last_name DROP NOT NULL;  # requires approval
  - name: contract
    change: Stop writing full_name, then rename it to full_name_deprecated.
    approval: required, because readers still pinned to full_name break
    rollback: Re-enable full_name writes derived from the split columns.  # requires approval
  - name: cleanup
    change: ALTER TABLE users DROP COLUMN full_name_deprecated;
    approval: required, irreversible without a restore
    rollback: Restore from the verified backup, rehearsed on a staging copy.  # requires approval
```

Reconciliation queries (PostgreSQL), run after the backfill, during dual read,
and before cutover:

```sql
-- 1. Rows not yet backfilled. Accept: 0.
SELECT count(*) AS missing_split
FROM users
WHERE first_name IS NULL OR last_name IS NULL;

-- 2. Rows whose split columns do not reconstruct full_name. Accept: no rows.
--    Valid only if the split rule is lossless for this data; otherwise compare
--    against the output of the shared split function.
SELECT id
FROM users
WHERE first_name IS NOT NULL
  AND full_name IS DISTINCT FROM btrim(concat_ws(' ', first_name, last_name))
LIMIT 100;

-- 3. Sampled mismatch rate during dual read (block sample of about 1% of pages).
SELECT count(*) FILTER (
         WHERE full_name IS DISTINCT FROM btrim(concat_ws(' ', first_name, last_name))
       )::float / NULLIF(count(*), 0) AS mismatch_rate
FROM users TABLESAMPLE SYSTEM (1);
```

Record each check's command, result summary, and time in the plan's
Verification section so the cutover decision is auditable without rerunning
queries. Return ids, not regulated values.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
- Never weaken a test, check, or threshold to make work pass.
- Never run a data or traffic rollback (down migration, flag flip, restore,
  traffic shift) without explicit approval for that step. Halting a stage this
  session started is allowed.
- Stop for approval before irreversible operations: `DROP`, destructive
  `DELETE`, format overwrites without a backup, and API removals without a
  deprecation period. Present the operation, blast radius, backup evidence, and
  restore drill result.
- Never expand and contract in the same release, and never bundle several
  stages into one deploy.
- Run backfills with the least-privileged role that can do the work, never a
  superuser. Keep credentials and tokens out of plans and evidence; use
  placeholders for the project's secret store.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The migration tool lists the expected pending migrations (for example
  `alembic history`, `knex migrate:list`, `flyway info`).
- Each stage applies to a disposable or staging copy first, and its rollback is
  rehearsed there.
- Reconciliation queries return their accepted values at each checkpoint.
- One smoke check per consumer class passes against the new path.
- The project's type check, lint, and tests pass.

## Report

- **Migration:** kind, source and target state, and the stages executed so far.
- **Consumers:** each producer and consumer, with the search used to find them.
- **Evidence:** preflight results, reconciliation output, and the cutover
  decision against its criterion.
- **Rollback readiness:** flag paths, backup age, restore drill date, and
  approvals obtained or still needed.
- **Remaining work:** contract and cleanup stages with their approval points.
- **Not verified:** checks that could not run and why.

Save the plan where the project keeps design or operations documents (for
example `docs/migrations/`); ask if there is no convention.

<!-- handoff: data-migration-plan -->
```markdown
# Data migration plan: [change name]

## Current and target state
## Preflight
## Rollout
## Rollback
## Verification
## Handoff

**Changed contract:** nullability, defaults, fields, endpoints, or keys that change.
**Files / systems affected:** schemas, migrations, services, jobs, and clients.
**Evidence and tests:** rehearsals, reconciliation results, and smoke checks.
**Risks / rollback:** irreversible stages, data-loss risks, and approval points.
**What the next agent needs:** the current stage, pending approvals, and next checks.
```

## Optional delegation

The `migration-planner` subagent can review the plan for compatibility gaps and
lock hazards before any stage runs; re-check its findings against the code. The
`database-architect` subagent can review schema changes. One agent can complete
this workflow alone.
