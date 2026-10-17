---
name: data-pipeline-design
description: "Design batch or incremental ETL and ELT pipelines and warehouse models: grain, partitioning, idempotent loads, late-arriving data, data quality tests, PII controls, and cost monitoring, before building them. Use when adding or changing a dbt model, warehouse table, scheduled transformation, or ingestion job. Not for transactional schema design (use the database-design skill) or event-sourced stores (use the event-sourcing-architecture skill)."
---

# Data Pipeline Design

Produce a pipeline specification that a builder can implement without guessing:
target models with a declared grain, a load strategy that is safe to re-run,
quality tests that gate publishing, and PII controls. The stance is
**idempotent by construction, design before build**: every run can be repeated
and yields the same target state, and this skill never runs production loads,
backfills, or full refreshes without approval.

Follow the project's warehouse (PostgreSQL, BigQuery, Snowflake, DuckDB, or
other), transformation framework (dbt, SQL, Spark, Python), and orchestrator.

## When to use

- A new or changed dbt model, warehouse table, or scheduled transformation.
- A new ingestion job from an operational database, API, files, or a stream.
- Duplicates, missed late updates, or cost blowups in an existing pipeline that
  call for a redesign of the load strategy.

## When not to use

- Transactional (OLTP) tables and indexes: use the `database-design` skill.
- Changing an operational table that live services depend on: use the
  `safe-migration` skill.
- A single slow existing query: use the `query-optimization` skill.
- Test or demo data: use the `synthetic-data-generation` skill.
- Independent review of a pipeline design: delegate to the `data-engineer`
  subagent.
- Answering a one-off business question from existing data: use the
  `analyze-data` skill.
- Training and shipping a machine-learning model: use the
  `ml-model-development` skill.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous.

- Warehouse engine, framework, and orchestrator, from `dbt_project.yml`,
  profiles and targets, and the orchestrator's DAG or job definitions.
- Each source: system, volume, and change pattern (append-only, updates in
  place, hard deletes, CDC feed); which timestamps exist and whether they are
  reliable; how late data can arrive.
- Downstream consumers, their query patterns, and the freshness they need.
- PII classification, retention, erasure obligations, and the governance owner.
- Cost constraints: compute or bytes-scanned budget per run, if the project has one.

## Workflow

1. **State constraints and unknowns:** volume, freshness need, privacy,
   retention, and late-arrival behavior. Record guesses as assumptions.
2. **Declare the grain** of every target table in one sentence ("one row per
   charge"). Choose a star schema or a wide table from the consumers' query
   patterns, and trace every target column to a source field or a documented
   derivation.
3. **Partition and cluster.** Partition by the column most queries filter on
   (usually the event date). Cluster on the highest-selectivity filter or join
   columns.
4. **Pick the load strategy:**
   - Full refresh for small tables.
   - Incremental merge on a unique key when rows can change after load.
   - Insert-overwrite of recent partitions: cheaper, but correct only when
     changes land in those partitions.
   - Append with deduplication for immutable events.
   - CDC apply when the source hard-deletes rows; timestamp-based increments
     never see deletes, so otherwise schedule a periodic reconciliation.
5. **Design the watermark and late data.** Derive the watermark from the target
   (for example `max(updated_at)`) minus a lookback sized to observed lateness,
   so a failed run is recovered by the next one. State what happens to rows
   older than the lookback.
6. **Make every run idempotent and deterministic.** Merge on stable keys,
   deduplicate within each batch (a merge fails or duplicates when the source
   has several rows per key), break ties with a deterministic column, and keep
   the run clock (`current_timestamp`) out of business columns.
7. **Design quality tests and their failure policy.** At minimum: `not_null`
   and `unique` on the grain, relationships to dimensions, accepted values,
   ranges, a volume check, and source freshness. Failing `error` tests block
   publishing or downstream models; `warn` tests notify.
8. **Design PII handling.** Classify every source column and drop what
   consumers do not need. Plain `sha256(email)` is pseudonymization, not
   anonymization: anyone holding a list of candidate emails can hash them and
   match (a dictionary attack). Use a keyed HMAC with a key from the secret
   manager, computed at ingestion before data lands in the warehouse, or the
   warehouse's keyed or deterministic-encryption functions if it has them. The
   output is still personal data, so erasure requests must still reach raw and
   curated layers. Restrict any raw PII columns with column-level access
   policies.
9. **Plan monitoring and cost:** row counts per run, duration, bytes scanned,
   schema drift, and failure alerts, with budgets from the project.
10. **Plan the rollout:** initial backfill (cost estimate, run in chunks),
    schedule, consumer cutover, and rollback. Write it as the handoff below.

## Reference example: incremental dbt model

Illustrative dbt on BigQuery; adapt functions and config to the project's
adapter. The source already carries `customer_email_token`, computed at
ingestion.

```sql
-- models/marts/fct_charges.sql
-- Grain: one row per charge_id.
{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='charge_id',
    partition_by={'field': 'charge_date', 'data_type': 'date'},
    cluster_by=['customer_id', 'status']
  )
}}

with source as (
    select
        charge_id,
        customer_id,
        date(created_at) as charge_date,
        amount_cents,
        currency,
        status,
        customer_email_token,
        created_at,
        updated_at
    from {{ source('payments', 'charges') }}
    {% if is_incremental() %}
    -- Reprocess a 3-day lookback from the newest row already loaded, so late
    -- updates are absorbed and a failed run is recovered by the next run.
    where updated_at >= (
        select timestamp_sub(max(updated_at), interval 3 day) from {{ this }}
    )
    {% endif %}
),

ranked as (
    -- A merge needs at most one source row per key: keep the newest version.
    -- Add a tiebreaker column if updated_at can repeat for one charge.
    select
        *,
        row_number() over (
            partition by charge_id
            order by updated_at desc
        ) as version_rank
    from source
)

select
    charge_id, customer_id, charge_date, amount_cents, currency, status,
    customer_email_token, created_at, updated_at
from ranked
where version_rank = 1
```

On BigQuery a merge scans the target to match keys. If updates only ever land
in recent partitions, `insert_overwrite` on those partitions (or
`incremental_predicates`, where the adapter supports it) costs less; check the
adapter documentation for your dbt version.

Keyed token at ingestion (illustrative Python):

```python
import hashlib
import hmac


def email_token(email: str, key: bytes) -> str:
    """Keyed pseudonym for joins. Load the key from the secret manager."""
    normalized = email.strip().lower()
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
```

Quality tests. dbt 1.8 and later accept `data_tests:` (older versions use
`tests:`), and recent versions prefer test inputs nested under `arguments:`;
follow the syntax of the project's dbt version.

```yaml
# models/marts/schema.yml
version: 2

sources:
  - name: payments
    tables:
      - name: charges
        loaded_at_field: updated_at
        freshness:
          warn_after: {count: 12, period: hour}
          error_after: {count: 24, period: hour}

models:
  - name: fct_charges
    description: One row per charge.
    data_tests:
      - dbt_utils.expression_is_true:
          expression: "customer_email_token is null or length(customer_email_token) = 64"
    columns:
      - name: charge_id
        data_tests: [not_null, unique]
      - name: customer_id
        data_tests:
          - not_null
          - relationships:
              to: ref('dim_customers')
              field: customer_id
      - name: status
        data_tests:
          - accepted_values:
              values: ['succeeded', 'pending', 'failed', 'refunded']
      - name: amount_cents
        data_tests:
          - dbt_utils.expression_is_true:
              expression: ">= 0"  # column level: dbt_utils prepends the column name
```

`expression_is_true` filters row by row, so it cannot check aggregates such as
volume. Use a singular test, which fails when it returns any row:

```sql
-- tests/assert_fct_charges_volume.sql
-- Fails when yesterday's rows fall below half the prior 7-day daily average.
with daily as (
    select charge_date, count(*) as row_count
    from {{ ref('fct_charges') }}
    where charge_date between date_sub(current_date(), interval 8 day)
                          and date_sub(current_date(), interval 1 day)
    group by charge_date
),

baseline as (
    select avg(row_count) as avg_rows
    from daily
    where charge_date < date_sub(current_date(), interval 1 day)
)

select b.avg_rows, coalesce(y.row_count, 0) as yesterday_rows
from baseline as b
left join daily as y
    on y.charge_date = date_sub(current_date(), interval 1 day)
where coalesce(y.row_count, 0) < 0.5 * b.avg_rows
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  production runs, backfills, `--full-refresh` (it rebuilds the table), table
  drops, mass deletes, and unpartitioned full scans of large tables.
- Never weaken a test, check, or threshold to make work pass. Do not downgrade
  an `error` test to `warn` without the owner's agreement.
- Raw PII never lands in curated layers. Keys and credentials stay in the
  secret manager; designs refer to them by name.
- Use the project's orchestrator and framework; do not introduce a second one.
- Pipeline roles get write access only to their target schemas and read access
  only to declared sources.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately against a development target, and
report its real result; never chain alternatives with `||`.

- The project parses and compiles (for example `dbt parse`, then
  `dbt compile --select fct_charges`).
- The changed models build and their tests pass (for example
  `dbt build --select fct_charges+ --target dev`).
- Idempotency: running the incremental model twice with no new source data
  leaves row counts unchanged and the grain tests passing.
- Equivalence: an incremental build matches a `--full-refresh` build of the same
  data in a development schema, checked with `EXCEPT DISTINCT` in both
  directions (empty both ways).
- Source freshness runs (for example `dbt source freshness`).
- The project's lint and unit tests pass.

## Report

- **Models:** grain, columns and lineage, partitioning and clustering rationale.
- **Load strategy:** watermark, lookback, merge keys, dedup, delete handling.
- **Quality tests:** each test, its severity, and what it protects.
- **PII controls:** classification, tokenization method and key ownership,
  access policies, erasure path.
- **Monitoring and cost:** metrics, alerts, and per-run budget.
- **Not verified:** checks that could not run and why.

Write the specification as a data-migration-plan handoff: current and target
state cover sources and target models, and rollout covers the initial backfill,
schedule, and consumer cutover. Save it where the project keeps design
documents (for example `docs/data/`); ask if there is no convention.

<!-- handoff: data-migration-plan -->
```markdown
# Data migration plan: [pipeline name]

## Current and target state
## Preflight
## Rollout
## Rollback
## Verification
## Handoff

**Changed contract:** grain, columns, and semantics consumers will see.
**Files / systems affected:** models, sources, jobs, and downstream dashboards.
**Evidence and tests:** dev builds, test results, and equivalence checks.
**Risks / rollback:** backfill cost, late data, PII exposure, and the revert path.
**What the next agent needs:** approvals, schedule, and open questions.
```

## Optional delegation

The `data-engineer` subagent can review the design or existing models for
idempotency, quality coverage, and governance gaps; verify its findings before
acting. One agent can complete this workflow alone.
