---
name: production-data-fix
description: "Correct bad production data after a bug or operational mistake with a one-off UPDATE, DELETE, INSERT, or reprocessing run: confirm the cause is fixed, verify the selection on a replica, back up affected rows, run a reviewed, idempotent, batched script under approval, decide each side effect, and verify and record the result. Use when production rows are wrong, missing, or duplicated and must be repaired. Not for schema changes (use the safe-migration skill) or active incidents (use the incident-triage skill)."
---

# Production Data Fix

Repair data that a bug or a mistake damaged, without damaging more of it. The
stance is **cause fixed, scope proven, backup taken, approval given**: no row
changes until the source of bad rows is stopped, the selection is verified
read-only, the old values are saved, and a person has approved the exact script.
The agent prepares and rehearses; production writes happen only with explicit
approval.

## When to use

- Rows were written with wrong values, deleted by mistake, duplicated, or never
  created, and the data must be corrected.
- Records must be reprocessed (recomputed, re-sent, re-synced) after a bug.
- Someone proposes "just run an UPDATE in the console".

## When not to use

- The cause is unknown or still writing bad rows: use the `systematic-debugging`
  skill first.
- An active incident: use the `incident-triage` skill to stabilize, then return
  here for the repair.
- Schema changes and the backfills that belong to them: use the `safe-migration`
  skill.
- Routine replay of dead-lettered jobs: use the `background-jobs-and-queues`
  skill.
- Deleting personal data for erasure or retention: use the
  `data-retention-and-erasure` skill.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous and would
change the result.

- The bug, the fix commit, and when the fix was deployed (UTC); when the bug
  started writing bad data.
- The correct value for each affected row and its source of truth (audit log,
  event history, provider records, a backup, a recomputation).
- Database engine and version, table sizes, write rate, replicas or snapshots
  available, and replication lag limits.
- How production access works: roles, change approval, required reviewers, a
  two-person rule, and allowed run windows.
- Every system that reacts to these rows: events or outbox, webhooks, emails and
  notifications, caches, search indexes, analytics or change-data-capture,
  downstream services, audit logs, and triggers.
- Where the project keeps operational scripts, and whether it prefers SQL or an
  application script runner (a Django management command, a Rake task).

## Workflow

1. **Confirm the cause is fixed.** The fix must be deployed, and the selection
   predicate limited to rows written after the deploy must return zero. If bad
   rows are still appearing, stop: repairing data while the bug writes more is
   a loop.
2. **Define the correction.** For each row, the correct value and where it
   comes from. Rows whose correct value cannot be established go to a
   separate list for manual review; never guess.
3. **Write the selection predicate** with a reason for every condition: the bad
   state itself (so reruns skip fixed rows), the time window from bug start to
   fix deploy in UTC, tenant or account scope, and exclusions (soft-deleted
   rows, test accounts, rows users have changed since). Identify affected rows
   positively rather than "everything except".
4. **Verify read-only on a replica or snapshot.** Check replica lag first (on a
   PostgreSQL replica, `now() - pg_last_xact_replay_timestamp()`). Run the count,
   a sample of about 20 rows ordered by key, and counts by day, tenant, and
   status. Compare them with independent evidence (error logs, tickets, how
   often the bug triggered) and inspect rows just outside the boundaries. Share
   IDs, not personal data.
5. **Write the fix as a reviewed script**, never typed into a production
   console. Use the `write-ops-script` skill for its structure (dry run by
   default, logging, confirmation). Choose the mechanism deliberately: SQL is
   explicit and fast but bypasses application validations, callbacks, and
   events; application code runs them, with hidden side effects and often row
   by row.
6. **Make it idempotent and batched.**
   - Each write re-checks the bad state in its `WHERE`, so a rerun or overlap
     changes nothing twice and rows changed since the backup are skipped.
   - Batch by primary key with a keyset cursor, one transaction per batch, sized
     in rehearsal so each batch finishes well inside the statement timeout (for
     example 500 to 5,000 rows). One huge transaction holds row locks until it
     ends, bloats tables, grows replication lag, loses all progress on any
     error, and in some engines (InnoDB among them) rolls back slowly.
   - Pause between batches and print the last completed ID so a stopped run can
     resume.
   - Deletes: move rows to the backup first, or soft-delete. Inserts: use a
     natural unique key with `ON CONFLICT DO NOTHING`. Reprocessing: enqueue jobs
     for the affected IDs at a throttled rate through idempotent handlers.
7. **Back up affected rows first.** Copy the full rows (at least the key and
   every column you change) into a backup table in a schema set aside for data
   fixes, named after the ticket, or export them to approved storage. Its count
   must match the selection, and it becomes the frozen worklist. Write the undo
   script now and rehearse it. The backup holds the same sensitive data as the
   source: restrict access, record its location, and agree a drop date; dropping
   it later is a separate approved step.
8. **Decide every side effect explicitly.** For each system from Inputs, write
   "trigger", "suppress", or "handle separately", and how:
   - Events, webhooks, and change-data-capture: will consumers see the fix, and
     should they?
   - Emails, SMS, and push: a "your invoice is paid" message to thousands of old
     customers is its own incident. Customer-facing messages need explicit
     sign-off.
   - Caches and search indexes: invalidate or reindex the affected IDs.
   - Analytics, warehouse, billing, ledgers, and other downstream systems:
     correct them too, or record why not. For money, post compensating entries
     rather than editing history.
   - Audit logs, triggers, and `updated_at`: bumping `updated_at` can wake sync
     jobs that poll on it. Never disable triggers or constraints
     (`ALTER TABLE ... DISABLE TRIGGER`, `session_replication_role`) without
     explicit approval and the database owner.
9. **Rehearse on staging or a restored copy** with production-like volume: run
   the backup, fix, verification, and undo. Record time per batch, lock waits,
   and replication lag, and repeat until the run is clean.
10. **Get approval** for the exact script. Present the cause and fix deploy, the
    predicate, counts and sample IDs, the correction source, the script and its
    reviewer, the backup and undo, side-effect decisions, rehearsal results, the
    window, stop conditions, and who runs it. Production runs only after
    explicit approval, in the agreed window, with a second person present if the
    project requires it, under a least-privilege role (the needed `SELECT` and
    `UPDATE` grants plus `CREATE` on the backup schema; never a superuser or the
    schema owner), with `statement_timeout` and `lock_timeout` set.
11. **Run and watch.** Back up, then run batches while watching lock waits,
    replication lag (`replay_lag` in `pg_stat_replication`), application error
    rates, and queues fed by side effects. Stop between batches if rows per
    batch exceed what the backup predicts, lag passes the limit, errors appear,
    or anything surprises you; resume from the last completed ID.
12. **Verify** (see Verification), then **record** the change (see Report).

## Worked example: paid invoices marked overdue (illustrative PostgreSQL)

From 2026-10-01 09:00 UTC until the fix deployed at 2026-10-03 14:00 UTC, a bug
marked paid invoices `overdue`. Correct state: `status = 'paid'`,
`overdue_at` NULL. Run each file separately. In SQL, the approval marker is
`-- requires approval`.

```sql
-- check.sql: read-only, on a replica or snapshot. Compare with logs.
SELECT count(*)
FROM invoices AS i
WHERE i.status = 'overdue'
  AND i.overdue_at >= '2026-10-01 09:00+00'
  AND i.overdue_at <  '2026-10-03 14:00+00'
  AND EXISTS (SELECT 1 FROM payments AS p
              WHERE p.invoice_id = i.id AND p.status = 'succeeded');
-- Also: a 20-row sample of ids ordered by id, and the same count with
-- overdue_at >= the fix deploy time (expect 0).

-- backup.sql: freezes the worklist and the old values. Run once.
CREATE TABLE datafix.inc1234_invoices_backup AS   -- requires approval
SELECT i.*
FROM invoices AS i
WHERE i.status = 'overdue'
  AND i.overdue_at >= '2026-10-01 09:00+00'
  AND i.overdue_at <  '2026-10-03 14:00+00'
  AND EXISTS (SELECT 1 FROM payments AS p
              WHERE p.invoice_id = i.id AND p.status = 'succeeded');
ALTER TABLE datafix.inc1234_invoices_backup ADD PRIMARY KEY (id);   -- requires approval

-- fix_batch.sql: one keyset batch; the driver runs it in its own transaction.
WITH batch AS (
    SELECT b.id
    FROM datafix.inc1234_invoices_backup AS b
    WHERE b.id > :last_id
    ORDER BY b.id
    LIMIT 1000
), updated AS (
    UPDATE invoices AS i   -- requires approval
    SET status = 'paid', overdue_at = NULL
    FROM batch
    WHERE i.id = batch.id
      AND i.status = 'overdue'   -- re-check: skip rows fixed or changed since
      AND EXISTS (SELECT 1 FROM payments AS p
                  WHERE p.invoice_id = i.id AND p.status = 'succeeded')
    RETURNING i.id
)
SELECT (SELECT max(id) FROM batch) AS next_id,
       (SELECT count(*) FROM updated) AS updated_rows;
```

The cursor advances by the batch's highest backup ID, not the updated rows, so a
batch where every row is skipped does not end the run early.

```bash
#!/usr/bin/env bash
# run_fix.sh: one transaction per batch; resume with START_AFTER_ID.
# The connection string names the least-privilege data-fix role; keep the
# password in .pgpass or the secret manager, not in the URL or shell history.
set -euo pipefail
export PGOPTIONS='-c statement_timeout=30s -c lock_timeout=2s'
export PGAPPNAME='datafix-inc1234'
last_id="${START_AFTER_ID:-0}"
while true; do
  result=$(psql "$DATAFIX_DATABASE_URL" -X -q -At -v ON_ERROR_STOP=1 \
    -v last_id="$last_id" -f fix_batch.sql)   # requires approval
  IFS='|' read -r next_id updated <<<"$result"
  if [ -z "$next_id" ]; then break; fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) after=$last_id through=$next_id updated=$updated"
  last_id="$next_id"
  sleep 1   # pause between batches; watch replication lag and lock waits
done
```

`undo_batch.sql` has the same shape: it restores `status` and `overdue_at` from
the backup table for rows still in the fixed state. Verification re-runs
`check.sql` (expect 0) and joins the backup table to `invoices`, grouped by
status, to show every backed-up row is fixed or was skipped for a known reason.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never write to production without explicit approval of the exact script, and
  mark every production-writing command `# requires approval`
  (`-- requires approval` in SQL). Read-only checks run on a replica or snapshot
  where one exists.
- Never change data before the cause is fixed, before the backup is verified,
  or with a predicate that has not been counted read-only.
- Never run a data fix as a superuser or the schema owner, in one unbounded
  transaction, or without statement and lock timeouts.
- Never disable triggers, constraints, or audit logging to make a fix easier
  without explicit approval.
- Never send customer-facing messages as a side effect without sign-off.
- Never put personal data from affected rows into tickets, chat, or the report;
  use IDs and counts.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Run each check separately and report its real result; never chain alternatives
with `||`.

- Rehearsal on staging or a restored copy: backup count equals the selection,
  the fix leaves zero matching rows, and the undo restores the original values.
- In production, after the run: the original predicate returns zero.
- Reconciliation: every backed-up row is fixed or on the skipped list with a
  reason; status counts changed by exactly the number of fixed rows; totals
  (amounts, balances) match the source of truth.
- Spot checks of sampled IDs through the application or API show correct data.
- Each side effect happened where it was meant to and nowhere else (no
  unexpected emails, events, or webhook deliveries).
- The regression test for the original bug passes in the project's suite.

## Report

- **Cause and fix:** the bug, fix commit, and deploy time (UTC).
- **Scope:** the predicate verbatim, expected and actual counts, and rows set
  aside for manual review.
- **Execution:** script version, reviewer, approver, operator, role, and start
  and end times (UTC).
- **Verification:** remaining count, reconciliation results, and spot checks.
- **Not verified:** checks that could not run, and follow-ups with owners.

Record the change where the project keeps operational records (the incident or
ticket, or for example `docs/operations/`); ask if there is no convention.

```markdown
# Data fix: TICKET-ID short description

- Cause and fix: bug, fix commit, deployed at (UTC)
- Scope: predicate (verbatim), expected and actual row counts
- Correction: new values and their source of truth
- Backup: location, row count, who can access it, drop date
- Side effects: each system, triggered or suppressed, and how
- Execution: script and version, reviewer, approver, operator, role, window (UTC)
- Verification: remaining count, reconciliation, spot checks
- Undo: script location and rehearsal result
- Follow-ups: owner and due date for each
```

## Optional delegation

The `debugger` subagent can confirm the root cause and that the fix stops new
bad rows. The `migration-planner` subagent can review the script for lock
hazards, batch sizing, and rollback, and the `reviewer` subagent can give it the
second review. The workflow above stays complete for a single agent.
