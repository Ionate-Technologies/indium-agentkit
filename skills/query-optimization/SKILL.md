---
name: query-optimization
description: "Diagnose and fix an existing slow database query, PostgreSQL first with MySQL notes, by capturing its real parameters, reading EXPLAIN ANALYZE plans, and verifying a targeted index, rewrite, or statistics fix. Use when a known query, endpoint, or job is slow, a plan regressed, or N+1 queries or deep OFFSET pagination appear. Not for new schema design (use the database-design skill) or general application profiling (use the performance-optimization skill)."
---

# Query Optimization

Make one existing slow query fast, with a before-and-after plan as proof. The
stance is **plan before fix**: no index or rewrite until the plan, run with
real parameters on realistic data, shows where the time goes.

## When to use

- A specific query, endpoint, report, or background job is slow and the database
  is the suspected cost.
- A query got slower after a deploy, data growth, or a database upgrade (a plan
  regression).
- Logs or traces show N+1 query patterns, deep `OFFSET` pagination, or a
  statement dominating `pg_stat_statements`.

## When not to use

- Designing new tables, constraints, or access paths: use the `database-design`
  skill; delegate a design review to the `database-architect` subagent.
- The slowness is not yet attributed to the database: use the
  `performance-optimization` skill to profile first.
- Rolling out the resulting index or schema change: use the `safe-migration`
  skill for the rollout plan.

## Inputs to gather

Discover from the repository and monitoring; ask only for what is missing.

- The exact statement as executed, with real parameter values. Sources:
  `pg_stat_statements` (normalized, so constants appear as `$1`), the slow-query
  log (`log_min_duration_statement` in PostgreSQL, `slow_query_log` in MySQL),
  the `auto_explain` module, APM traces, or ORM debug logging.
- Frequency, latency target, and when it became slow. Use the project's SLO; for
  example "p95 under 100 ms for this endpoint".
- Database engine and version, table sizes, existing indexes (`\d table` in
  psql, `SHOW INDEX FROM table` in MySQL), and the migration tool in use.
- A non-production database with production-like data volume and distribution.

## Workflow

1. **Find the real query.** Rank by total time to find the largest load, and by
   mean time for user-facing latency. In PostgreSQL 13 and later,
   `SELECT calls, total_exec_time, mean_exec_time, query FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;`
   (older versions name the columns `total_time` and `mean_time`). In MySQL,
   use `performance_schema.events_statements_summary_by_digest`. Recover the
   actual parameter values from logs or traces; a plan for the wrong values can
   mislead completely.
2. **Reproduce off production.** Run the statement on a production-like copy,
   not a small fixture database: plans depend on row counts and data
   distribution. Record the parameters, the dataset, and whether the cache was
   warm.
3. **Capture the plan.** In PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS) <statement>;`.
   `ANALYZE` executes the statement. For `INSERT`, `UPDATE`, or `DELETE`, wrap
   it in `BEGIN;` ... `ROLLBACK;`. The rollback does not undo sequence
   increments or external side effects of triggers, and row locks block other
   sessions until it runs. Never run `EXPLAIN ANALYZE` against production
   without explicit approval. In MySQL
   8.0.18 and later, `EXPLAIN ANALYZE` also executes the statement;
   `EXPLAIN FORMAT=TREE` shows the plan without running it.
4. **Read the plan** from the most expensive node outward:
   - Estimated versus actual rows. A large gap (an order of magnitude is a
     common warning sign) points to stale or missing statistics, correlated
     columns, or a non-sargable predicate. Actual rows are averaged per loop, so
     multiply by `loops`.
   - `Seq Scan` on a large table with a high `Rows Removed by Filter`.
   - `Nested Loop` with a large outer side, so the inner node runs thousands of
     times.
   - `Sort Method: external merge  Disk: ...` or hash `Batches` above 1: the
     operation spilled past `work_mem`.
   - `Buffers: shared read=...` (from disk or OS cache) versus `hit=...`, and
     a high `Heap Fetches` count on an index-only scan, which means many pages
     are not marked all-visible and the table needs vacuuming.
5. **Choose the smallest fix** that addresses what the plan shows:
   - **Composite index in the right order:** equality columns first, then the
     range or `ORDER BY` column, so the index both filters and returns rows in
     order. An index on `(created_at, tenant_id)` serves
     `WHERE tenant_id = $1 ORDER BY created_at` poorly; `(tenant_id, created_at)`
     serves it well.
   - **Partial index** (`... WHERE status = 'open'`) when queries always target
     a small subset. The query's `WHERE` clause must imply the index predicate,
     which a parameter such as `status = $2` under a generic plan does not.
     **Covering index** (`INCLUDE (...)` in PostgreSQL 11 and later) to enable an
     index-only scan. InnoDB secondary indexes already carry the primary key.
   - **Sargable predicates:** replace `WHERE date(created_at) = $1` with a
     half-open range (`created_at >= $1 AND created_at < $2`); index the
     expression for `lower(email) = $1`; a leading-wildcard `LIKE '%term'`
     cannot use a B-tree, so use a trigram index (`pg_trgm`) or full-text
     search; fix type or collation mismatches between column and parameter
     (for example a string column compared with a number in MySQL).
   - **N+1 queries:** collapse them into one join or one batched load
     (`WHERE id = ANY($1)` in PostgreSQL, `IN (...)` in MySQL, or the ORM's
     eager loading such as `select_related`, `prefetch_related`, `selectinload`,
     or `includes`).
   - **Keyset pagination** instead of large `OFFSET`:
     `WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 50`
     with an index on `(created_at, id)`. In MySQL, check the plan; the expanded
     form `created_at < $1 OR (created_at = $1 AND id < $2)` may use the index
     better.
   - **Stale statistics:** run `ANALYZE table_name;` (MySQL: `ANALYZE TABLE`).
     For correlated columns in PostgreSQL, consider `CREATE STATISTICS` or a
     higher per-column statistics target.
   - **Parameter-sensitive plans:** with skewed data (one tenant owns most
     rows), a cached generic plan can suit one value and hurt another. Reproduce
     with `PREPARE` and `SET plan_cache_mode = force_generic_plan;` (PostgreSQL
     12 and later), then fix with a partial index, a separate query path for the
     outlier, or `force_custom_plan` set for the session, role, or function
     that runs it.
6. **Weigh the write cost.** Every index slows inserts and updates, uses disk,
   and in PostgreSQL an update that changes an indexed column cannot be a HOT
   (heap-only tuple) update. Check for redundant or unused indexes before
   adding one: `pg_stat_user_indexes` with
   `idx_scan = 0` (MySQL: `sys.schema_unused_indexes`). Before calling an index
   unused, check when statistics were last reset, whether replicas use it (each
   keeps its own counters), and whether it enforces a unique or primary key
   constraint.
7. **Verify** with the same parameters and dataset (see Verification).
8. **Ship through migrations.** Add production indexes in the project's
   migration tool, never by hand. In PostgreSQL use `CREATE INDEX CONCURRENTLY`;
   it cannot run inside a transaction, so most migration tools need a
   per-migration opt-out of their wrapping transaction (check the tool's docs). A
   failed concurrent build leaves an `INVALID` index that must be dropped and
   retried. In MySQL, use online DDL (`ALGORITHM=INPLACE, LOCK=NONE`) or the
   project's online schema change tool. Use the `safe-migration` skill for
   rollout and rollback, and the `database-design` skill if the fix grows into a
   schema change.

## Worked example: equality, order, and limit (illustrative)

`SELECT id, total FROM orders WHERE customer_id = $1 AND status = 'open' ORDER BY created_at DESC LIMIT 20;`
takes about 400 ms. The plan (abbreviated) shows a full scan:

```text
Limit (actual time=412.3..412.3 rows=20 loops=1)
  ->  Sort (actual time=412.3..412.3 rows=20 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 27kB
        ->  Seq Scan on orders (cost=0.00..76081.00 rows=1180 width=16) (actual time=0.9..411.8 rows=1342 loops=1)
              Filter: ((customer_id = 4821) AND (status = 'open'::text))
              Rows Removed by Filter: 2398658
              Buffers: shared hit=1204 read=38877
```

Estimated rows (1180) are close to actual (1342), so statistics are fine; the
problem is the access path.
Only open orders are queried, so a partial index ordered for the sort fits:

```sql
CREATE INDEX CONCURRENTLY orders_customer_open_created_idx
    ON orders (customer_id, created_at DESC)
    WHERE status = 'open';
```

After the build, the same parameters give an index scan with no sort:

```text
Limit (actual time=0.05..0.11 rows=20 loops=1)
  ->  Index Scan using orders_customer_open_created_idx on orders (actual time=0.04..0.10 rows=20 loops=1)
        Index Cond: (customer_id = 4821)
        Buffers: shared hit=24
```

Buffers drop from about 40,000 to 24. Next, check the write cost on `orders`
and look for existing indexes that this one makes redundant.

## Guardrails

- Revert or delete only files, indexes, and settings you created in this
  session, and say so. Never discard someone else's uncommitted work.
- Ask before running anything against production, including `EXPLAIN ANALYZE`,
  `ANALYZE`, index builds, and setting changes. Prefer a replica or a restored
  copy.
- Never create or drop production indexes outside the migration process, and
  never drop an index based only on a single `idx_scan = 0` reading.
- Do not change global settings such as `work_mem` or `random_page_cost` to fix
  one query; scope settings to a session, role, or transaction and justify them.
- Do not add query hints or disable planner methods (`SET enable_seqscan = off`)
  in application code; use them only as diagnostic experiments.
- Never weaken a test, check, or threshold to make work pass. Redact personal
  data from copied parameters and query results.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The same statement with the same parameters on the same dataset: compare plan
  shape, actual rows, buffers, and execution time before and after. Run it
  several times and report the median, with warm and cold cache noted. Buffers
  are a steadier comparison than milliseconds.
- Representative other parameter values, including the largest tenant or the
  most common status, so the fix does not move the slowness elsewhere.
- Other frequent queries on the same table still use good plans.
- The migration applies cleanly in a non-production environment, and the
  project's test suite passes.
- After release, the statement's latency in `pg_stat_statements` or APM matches
  the improvement.

## Report

- **Query:** statement, parameters used, frequency, and source of evidence.
- **Diagnosis:** the plan node responsible, with before plan excerpt and numbers.
- **Fix:** the index, rewrite, or statistics change, and the migration that
  carries it.
- **Result:** before and after plans, buffers, and timings for the same
  parameters, plus other parameter values checked.
- **Trade-offs:** write cost, disk size, and redundant indexes found.
- **Not verified:** checks that could not run and why (for example no
  production-like dataset).

## Optional delegation

The `performance-profiler` subagent can confirm the database is the bottleneck
and record a baseline. The `database-architect` subagent can review a proposed
index or rewrite against the wider access patterns. The `migration-planner`
subagent can audit the index migration for lock hazards. The workflow above
stays complete for a single agent.
