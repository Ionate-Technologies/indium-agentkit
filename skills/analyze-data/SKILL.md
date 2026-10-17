---
name: analyze-data
description: "Answer a business or product question with SQL or a notebook against an approved read replica or warehouse: define the metric precisely, check row grain and join fan-out, handle NULLs, duplicates, and time zones, cross-check against a known number, state uncertainty, keep PII out of outputs, and limit query cost. Use when asked how many, how much, what changed, or why a metric moved, or when two reports disagree. Not for building pipelines (use the data-pipeline-design skill) or tuning slow queries (use the query-optimization skill)."
---

# Analyze Data

Answer a question with a number that survives scrutiny. The stance is **define
before querying, check before claiming**: a result is reported only with its
definition, the query that produced it, the checks it passed, and its caveats.
This skill only reads data, from an approved read replica or warehouse.

## When to use

- A business or product question: how many, how much, what share, what
  changed, or did a launch move a metric.
- A dashboard number is disputed, or two reports disagree.
- An ad hoc analysis or notebook ahead of a decision, launch review, or
  experiment readout.

## When not to use

- A recurring pipeline or warehouse model: use the `data-pipeline-design`
  skill.
- A query that is correct but slow: use the `query-optimization` skill.
- Defining or instrumenting tracking events: use the `product-analytics` skill.
- Correcting bad data: use the `production-data-fix` skill. This skill never
  writes.
- Training a predictive model: use the `ml-model-development` skill.

## Inputs to gather

Discover these from the repository and data catalog before asking. Ask the user
only about what remains ambiguous and would change the result.

- The question in the asker's words, the decision it informs, and the
  precision and deadline it needs.
- The approved source: which read replica, warehouse, or BI connection, and a
  read-only role. The production primary is off limits without explicit
  approval.
- Existing definitions: semantic-layer or metrics files, dbt models and their
  docs, dashboard SQL. Reuse the canonical definition when one exists.
- The reporting calendar: time zone, week start, fiscal periods, and known data
  incidents, backfills, or tracking changes.
- Exclusion rules: test and internal accounts, staff, bots, fraud, refunds,
  deleted users, sandbox environments.
- Cost limits per query (bytes or credits) and the approved destinations for
  results.

## Workflow

1. **Restate the question and define the metric.** Write it down before
   querying:
   - Numerator and denominator (for rates), the unit and grain (user, account,
     order, session), and the aggregation.
   - The time window as a half-open interval `[start, end)` in a named time
     zone.
   - Population filters and exclusions (test accounts, refunds, bots), and the
     comparison (prior period, control group, target).
   If a term is ambiguous ("active user": signed in, or did a key action?),
   ask, because it changes the answer.
2. **Pick the source.** Use the approved replica or warehouse with a read-only
   role. Prefer modeled, tested tables over raw ones, note their freshness (last
   load time), and confirm they cover the whole window.
3. **Check grain before joining.** State each table's grain ("one row per
   order") and verify it: `count(*)` against `count(distinct key)`. Note NULL
   rates in the columns you will use, min and max dates, duplicate keys, soft
   deletes, and history tables with several rows per entity (these need an
   as-of join on validity dates).
4. **Join without fan-out.** Joining to a table with several rows per key
   multiplies rows, so counts and sums double-count. Count rows and distinct
   base keys before and after every join; if rows grew, test with `EXISTS` or
   aggregate the many side to the base grain first. `count(distinct ...)`
   repairs a count but not a sum. With a `LEFT JOIN`, put conditions on the
   right-hand table in `ON`; in `WHERE` they silently make it an inner join.
5. **Handle NULLs and duplicates.**
   - `count(col)` skips NULLs and `count(*)` does not; `avg` ignores NULLs, so
     its denominator shrinks; `col <> 'x'` drops NULL rows.
   - `NOT IN (subquery)` returns no rows when the subquery yields a NULL; use
     `NOT EXISTS`.
   - Integer division truncates in some engines (PostgreSQL among them); cast
     to numeric and guard zero denominators with `nullif(denominator, 0)`.
   - Event tables often contain retries and replays; deduplicate on event ID.
6. **Get date boundaries and time zones right.** Use half-open ranges
   (`>= start and < end`); `between` on timestamps either misses most of the
   last day or includes the next midnight. Convert to the reporting time zone
   before truncating to day or week (PostgreSQL: `ts at time zone 'zone'` on a
   `timestamptz`; BigQuery: `DATE(ts, 'zone')`; check your engine). The day of
   a daylight-saving change has 23 or 25 hours. Label or exclude the current
   partial period, and expect recent days to still fill in with late data.
7. **Explore cheaply.** Select only the columns you need, filter on the
   partition column, and use `LIMIT` or sampling while exploring. On warehouses
   billed by bytes scanned, `LIMIT` alone may not reduce cost (in BigQuery it
   usually does not), so run a dry run or byte estimate first, and set the
   engine's per-query limit if it has one (for example BigQuery's maximum bytes
   billed or PostgreSQL's `statement_timeout`). Ask before any query whose
   estimate exceeds the budget.
8. **Sanity-check the result.** Do at least one, preferably two:
   - Reconcile to a known number: finance totals, the official dashboard, an
     admin console count, or last period's report.
   - Compute it a second way: from another table (orders versus payments) or
     another method (aggregate-then-join versus `EXISTS`).
   - Check magnitudes: shares between 0 and 1, segments summing to the total,
     and daily series without unexplained gaps or spikes.
   - Trace a few individual rows end to end.
   Explain every gap or disclose it; do not report around it.
9. **State uncertainty.** Report sample sizes. A 95% interval for a proportion
   is roughly p ± 1.96 × sqrt(p × (1 − p) / n) (use a Wilson interval when n is
   small or p is near 0 or 1). For a difference of two independent
   proportions, the interval is roughly
   (p1 − p2) ± 1.96 × sqrt(p1 × (1 − p1) / n1 + p2 × (1 − p2) / n2). For
   example, 4% versus 6% on 200 users each is a 2-point difference ± about 4.3
   points: not evidence of a change. A metric that moved after a launch may reflect
   seasonality, mix shift, or a tracking change, so make causal claims only
   from an experiment, and check segment mix when an aggregate moves (Simpson's
   paradox). Many segment comparisons will produce some large differences by
   chance.
10. **Keep personal data in the warehouse.** Aggregate there and output only
    aggregates. Never export PII (names, emails, phone numbers, addresses, IP
    addresses, or identifiers your policy treats as personal) to files, chat,
    tickets, or notebooks committed to git. Suppress small cells below the
    project's minimum group size. If row-level output is truly needed, ask, and
    use the approved destination.
11. **Present it reproducibly.** Lead with the answer (the number, its
    interval or caveat, and the as-of time), then the definition, source and
    freshness, checks performed, and caveats. Save the query with
    parameterized dates in the project's analysis folder or BI tool, or a
    notebook with personal-data outputs cleared.

## Worked example: join fan-out (illustrative PostgreSQL)

Question: revenue from September 2026 orders (New York time) that used a
discount code. `orders` has one row per order; `order_discounts` has one row
per code applied, and an order can use several. `is_test` is `NOT NULL` here;
with a nullable flag, `is_test is not true` keeps the NULL rows.

```sql
-- Wrong: an order that used two codes is joined twice, so both numbers inflate.
-- count(distinct o.order_id) would repair the count but not the sum.
select count(*) as orders, sum(o.amount_cents) as revenue_cents
from orders as o
join order_discounts as d on d.order_id = o.order_id
where o.created_at >= (timestamp '2026-09-01' at time zone 'America/New_York')
  and o.created_at <  (timestamp '2026-10-01' at time zone 'America/New_York')
  and not o.is_test;

-- Grain check on the table being joined: rows greater than orders means fan-out.
select count(*) as discount_rows, count(distinct order_id) as orders_with_discount
from order_discounts;

-- Fixed: stay at the order grain and test for a discount with EXISTS.
select count(*) as orders, sum(o.amount_cents) as revenue_cents
from orders as o
where o.created_at >= (timestamp '2026-09-01' at time zone 'America/New_York')
  and o.created_at <  (timestamp '2026-10-01' at time zone 'America/New_York')
  and not o.is_test
  and exists (select 1 from order_discounts as d where d.order_id = o.order_id);

-- When values from the many side are needed, aggregate it to the order grain first.
with discounts_per_order as (
    select order_id, count(*) as codes_used, sum(discount_cents) as discount_cents
    from order_discounts
    group by order_id
)
select count(*) as orders,
       sum(o.amount_cents) as revenue_cents,
       sum(d.discount_cents) as discount_cents
from orders as o
join discounts_per_order as d on d.order_id = o.order_id
where o.created_at >= (timestamp '2026-09-01' at time zone 'America/New_York')
  and o.created_at <  (timestamp '2026-10-01' at time zone 'America/New_York')
  and not o.is_test;
```

The fixed queries must agree on `orders` and `revenue_cents`; that agreement is
the second-method check. `timestamp '...' at time zone 'America/New_York'`
reads the literal as New York local time, so each boundary is a New York
midnight whatever the UTC offset is that day.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Read only. Run `SELECT` statements against an approved replica or warehouse
  with a read-only role. Querying the production primary, writing tables
  outside a personal scratch schema, or running long queries on a shared
  cluster needs explicit approval.
- Ask before any query whose dry-run or estimated cost exceeds the budget.
- Never export or paste PII. Share aggregates, with small cells suppressed.
- Never weaken a test, check, or threshold to make work pass, and never drop
  outliers or inconvenient rows without stating the rule and its effect.
- If your definition differs from the canonical metric, say so and show both
  numbers rather than silently redefining it.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Grain checks: before and after each join, the row count equals the distinct
  count of the base key.
- The result reconciles with a known number or a second method, and any gap
  is explained.
- Boundary checks: the first and last day of the window are each included
  once, in the reporting time zone, and the count of excluded test or internal
  rows is reported.
- The saved query or notebook reruns from a clean session and reproduces the
  result for the stated as-of time.
- Outputs, exported files, and notebook cells contain no personal data.
- If the analysis lives in the repository, the project's lint and notebook
  checks pass.

## Report

- **Answer:** the number, its interval or range, and the as-of time.
- **Definition:** numerator, denominator, grain, window and time zone, filters,
  and exclusions.
- **Source:** tables or models used, their freshness, and the replica or
  warehouse queried.
- **Query:** path to the saved query or notebook.
- **Checks:** grain and fan-out checks, reconciliation, and second method.
- **Caveats:** data gaps, small samples, causal limits, and differences from
  the canonical definition.
- **Cost:** bytes scanned or credits, when relevant.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `data-engineer` subagent can review the source models for grain, late
data, and known quality issues before you rely on them. The `explorer` subagent
can locate existing metric definitions and dashboard SQL in a large repository.
The workflow above stays complete for a single agent.
