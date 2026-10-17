---
name: database-design
description: "Design relational schemas, constraints, and indexes from real access patterns, plus a staged migration plan with reconciliation queries, defaulting to PostgreSQL. Use when adding or changing tables, columns, keys, relationships, or indexes, or when a feature needs a new data model. Not for executing a rollout (use the safe-migration skill) or tuning existing slow queries (use the query-optimization skill)."
---

# Database Design

Turn a feature's data needs into a schema whose critical invariants the database
enforces, a staged migration plan, and the queries that prove the migration
worked. The stance is **design and verify, never execute in production**: this
skill writes DDL, plans, and checks; running them against shared or production
databases waits for the operator.

PostgreSQL is the default. Follow the project's actual engine, ORM, and
migration tool.

## When to use

- A feature needs new tables, or changes to columns, keys, constraints,
  relationships, or indexes.
- Choosing indexes for known access paths before the code ships.
- Replacing or splitting an existing table while old and new application
  versions may run against the same database.

## When not to use

- Executing the staged rollout (backfill runs, dual writes, cutover, rollback):
  use the `safe-migration` skill. This skill produces the plan it executes.
- An existing query is slow: use the `query-optimization` skill.
- Warehouse or analytics models: use the `data-pipeline-design` skill.
- Event-sourced stores: use the `event-sourcing-architecture` skill.
- Independent review: delegate the model, constraints, and indexes to the
  `database-architect` subagent, and the rollout and lock hazards to the
  `migration-planner` subagent.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous and would
change the design.

- Engine and version, ORM, migration tool, and whether that tool wraps each
  migration in a transaction (manifests, migration directories, `AGENTS.md`).
- Existing schema and its naming, type, and index conventions (migration
  history and ORM models).
- Access patterns: the queries the feature will run (filters, sort order, joins),
  how often, and expected row counts. Derive them from the API contract and call
  sites; flag guessed selectivity as an assumption.
- Ownership or tenancy, retention, PII columns, and deletion obligations.
- Operational constraints: table sizes, write rate, replicas, deploy ordering,
  and whether old application versions keep running during the change.

## Workflow

1. **State uncertainties first.** Write down what is unknown about cardinality,
   retention, ownership, privacy, and access patterns. Record each as an
   assumption or open question in the plan.
2. **Model entities and invariants.** Define keys, foreign keys with a
   deliberate `ON DELETE`, `NOT NULL`, `CHECK`, and `UNIQUE`. Anything that must
   never be violated belongs in the database, not only in application code. Add
   lifecycle columns the project uses. Mark every PII column with its retention
   and deletion rule. Never store raw credentials: store a hash plus a lookup
   prefix, or a reference to the secret manager.
3. **Choose indexes from real access paths.** Each index names the query it
   serves, its column order (equality columns first, then range or sort
   columns), and its write cost. Consider partial and covering (`INCLUDE`)
   indexes. Skip redundant ones: a `UNIQUE` constraint already creates an index,
   and an index on `(a, b)` serves filters on `a` alone. No speculative indexes.
4. **Pick lock-safe DDL** for every statement that touches an existing table
   (see the reference below). Note each statement's lock and whether it
   rewrites or scans the table.
5. **Stage the migration.** Expand (additive only), backfill in bounded batches
   keyed by primary key, cut over only after reconciliation passes, and contract
   only after old application versions are retired. Never expand and contract
   in the same release. Write the rollback for each stage before any stage runs.
   The rollout mechanics belong to the `safe-migration` skill.
6. **Define verification queries before any production action:** missing rows,
   invariant violations, orphans, sampled value equivalence, and replication
   lag, each with a numeric acceptance threshold.
7. **Align with the contract.** Check nullability, defaults, uniqueness, delete
   behavior, and error behavior against the API contract and feature brief.
   Send any forced contract change back through the `api-design` skill.
8. **Write the plan** as the data-migration-plan handoff below, and trace every
   table, index, and stage to a requirement or access pattern.

## Lock-aware DDL on existing PostgreSQL tables

- `CREATE INDEX CONCURRENTLY` does not block writes, but it **cannot run inside
  a transaction block**. Most migration tools wrap each migration in a
  transaction by default, so that migration must opt out, for example Rails
  `disable_ddl_transaction!`, Django `atomic = False`, Alembic
  `op.get_context().autocommit_block()`, or Knex
  `exports.config = { transaction: false }`. Check your tool's documentation.
  Give each concurrent index its own migration. A failed concurrent build leaves
  an `INVALID` index: drop it (`DROP INDEX CONCURRENTLY`) and retry.
- A table created in the same migration is empty, so a plain `CREATE INDEX`
  there is fine and can stay inside the transaction.
- `ADD COLUMN` that is nullable or has a constant default is a metadata change
  (PostgreSQL 11+). A volatile default such as `clock_timestamp()` rewrites the
  table.
- Add foreign keys and `CHECK` constraints as `NOT VALID`, then run
  `VALIDATE CONSTRAINT` separately; validation takes a lock that does not block
  reads or writes.
- To make a large column `NOT NULL`: add `CHECK (col IS NOT NULL) NOT VALID`,
  validate it, then `SET NOT NULL` (PostgreSQL 12+ uses the valid check to skip
  the full scan), then drop the check.
- Changing a column type usually rewrites the table unless the types are binary
  compatible (for example `varchar(50)` to `text`). Prefer a new column plus
  backfill.
- Set `lock_timeout` in DDL sessions so a blocked `ALTER` fails fast instead of
  queuing and blocking every query behind it.

## Reference example

Illustrative PostgreSQL. Migration 1 creates new, empty tables, so plain
`CREATE INDEX` is safe inside the tool's transaction. `gen_random_uuid()` is
built in from PostgreSQL 13; `digest()` needs the `pgcrypto` extension.

```sql
CREATE TABLE api_keys (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- RESTRICT: deleting a team with live keys must fail loudly, not
    -- silently orphan or cascade-revoke credentials.
    team_id    uuid        NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
    name       text        NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    -- Store a lookup prefix and a hash; the raw secret is never persisted.
    key_prefix text        NOT NULL CHECK (char_length(key_prefix) = 8),
    key_hash   bytea       NOT NULL,
    status     text        NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'revoked', 'expired')),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    -- Revoked keys always have a revocation time, and only revoked keys do.
    CHECK ((status = 'revoked') = (revoked_at IS NOT NULL)),
    -- Authentication looks keys up by prefix; the constraint creates the index.
    CONSTRAINT api_keys_prefix_unique UNIQUE (key_prefix)
);

-- Serves "list a team's active keys, newest first" (every request).
-- Equality column first, then the sort column; partial to stay small.
CREATE INDEX api_keys_team_active_idx
    ON api_keys (team_id, created_at DESC)
    WHERE status = 'active';

-- Append-only usage, partitioned by month so retention drops partitions
-- instead of running mass DELETEs. Create partitions ahead of time (a
-- scheduled job or pg_partman); an insert with no matching partition fails.
CREATE TABLE api_key_usage (
    api_key_id    uuid        NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    recorded_at   timestamptz NOT NULL,
    request_count integer     NOT NULL CHECK (request_count >= 0),
    PRIMARY KEY (api_key_id, recorded_at)  -- must include the partition key
) PARTITION BY RANGE (recorded_at);

CREATE TABLE api_key_usage_2026_10 PARTITION OF api_key_usage
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
```

Backfill batch from `legacy_tokens`, run by a job rather than a schema
migration. The runner starts with the nil UUID and passes the returned
`next_cursor` as `$1` until no row comes back.

```sql
SET lock_timeout = '3s';        -- example budgets; use the project's
SET statement_timeout = '30s';

WITH batch AS (
    SELECT id, team_id, key_material, created_at
    FROM legacy_tokens
    WHERE id > $1 AND status = 'active'
    ORDER BY id
    LIMIT 5000                  -- bounded: sized to lock and replica-lag budgets
),
ins AS (
    INSERT INTO api_keys (id, team_id, name, key_prefix, key_hash, status, created_at)
    SELECT id, team_id, 'Legacy token', left(key_material, 8),
           digest(key_material, 'sha256'), 'active', created_at
    FROM batch
    ON CONFLICT (id) DO NOTHING -- idempotent: re-running a batch is safe
)
SELECT id AS next_cursor FROM batch ORDER BY id DESC LIMIT 1;
```

Verification queries with acceptance thresholds:

```sql
-- 1. Preflight: legacy prefixes that would violate api_keys_prefix_unique.
SELECT left(key_material, 8) AS prefix, count(*)
FROM legacy_tokens WHERE status = 'active'
GROUP BY 1 HAVING count(*) > 1;
-- Accept: no rows (otherwise choose a longer prefix before backfilling)

-- 2. Missing rows after the backfill.
SELECT count(*) AS missing
FROM legacy_tokens t
WHERE t.status = 'active'
  AND NOT EXISTS (SELECT 1 FROM api_keys k WHERE k.id = t.id);
-- Accept: missing = 0

-- 3. Sampled value equivalence (block sample of about 1% of pages).
SELECT count(*) AS mismatches
FROM legacy_tokens t TABLESAMPLE SYSTEM (1)
JOIN api_keys k ON k.id = t.id
WHERE k.key_hash <> digest(t.key_material, 'sha256');
-- Accept: mismatches = 0

-- 4. Orphans: needed only where a foreign key is missing or NOT VALID.
SELECT count(*) AS orphan_usage_rows
FROM api_key_usage u
LEFT JOIN api_keys k ON k.id = u.api_key_id
WHERE k.id IS NULL;
-- Accept: orphan_usage_rows = 0

-- 5. Replica lag, on the primary, before cutover.
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
FROM pg_stat_replication;
-- Accept: below the project's limit on every replica (for example 16 MiB)
```

The contract stage (`DROP TABLE legacy_tokens`) appears in the plan only behind
an explicit approval point, after cutover is verified and old versions retire.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  This skill never runs migrations, backfills, or rollback SQL against shared or
  production databases; it hands the plan to the operator.
- Never weaken a test, check, or threshold to make work pass.
- `DROP`, `TRUNCATE`, and column rewrites on populated tables appear in a plan
  only behind an approval point with a rehearsed rollback.
- Plan migration statements for a role with DDL rights on the target schema,
  not a superuser.
- Keep credentials and connection strings out of plans; use placeholders.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The migration tool's own check or lint passes on the new migration files.
- Each stage applies cleanly to a disposable database built from the current
  schema (for example `psql "$SCRATCH_DATABASE_URL" -v ON_ERROR_STOP=1 -f stage.sql`),
  and its down migration works there if the tool has one.
- The verification queries return their accepted values on seeded scratch data.
- `EXPLAIN` of each access-pattern query uses the intended index on realistic
  data volumes (an empty table always gets a sequential scan).
- The project's schema-dependent tests pass.

## Report

- **Schema:** tables and columns with per-table and per-index rationale.
- **Invariants:** what the database enforces and what remains in application code.
- **Access paths:** each query pattern and the index that serves it.
- **Lock assessment:** each statement's lock, rewrite or scan, and timeout budget.
- **Not verified:** checks that could not run and why.

Save the plan where the project keeps design documents (for example
`docs/migrations/`); ask if there is no convention.

<!-- handoff: data-migration-plan -->
```markdown
# Data migration plan: [change name]

## Current and target state
## Preflight
## Rollout
## Rollback
## Verification
## Handoff

**Changed contract:** nullability, defaults, uniqueness, and API effects.
**Files / systems affected:** schemas, migrations, services, and jobs.
**Evidence and tests:** dry runs, query results, and EXPLAIN output.
**Risks / rollback:** locks, data-loss risks, and the recovery path per stage.
**What the next agent needs:** approvals, sequencing, and open questions.
```

## Optional delegation

The `database-architect` subagent can review the model, constraints, and
indexes, and the `migration-planner` subagent can audit the staged plan for
compatibility and lock hazards, in parallel. One agent can complete this
workflow alone.
