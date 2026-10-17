---
name: data-retention-and-erasure
description: "Implement data retention and data-subject requests (erasure and access or export) across every store: a data map built from code and config, retention rules from the project's policy, hard delete, anonymization, or crypto-shredding, propagation to search, caches, analytics, processors, and backups, and idempotent, audited, verified jobs that respect legal holds. Use when building account deletion, export, or retention purge jobs, or when erasure misses a store. Not for a compliance readiness audit (use the compliance-audit skill)."
---

# Data Retention and Erasure

Make deletion and export reach every copy of a person's data, provably, and on
the schedule the policy sets. The stance is **erasure is a distributed write
that must be verified**: soft deletes, hidden rows, and hashed emails are not
erasure, and the privacy owner, not the engineer, decides periods and
exceptions.

## When to use

- Building "delete my account", admin erasure, or a data-subject access or
  export feature.
- Adding scheduled retention, such as purging old events, expiring inactive
  accounts, or removing a closed tenant's data.
- An audit or questionnaire found erasure that misses search, caches,
  analytics, processors, or backups.
- A new store or processor starts receiving personal data and must join the
  deletion and export paths.

## When not to use

- Assessing readiness against GDPR, SOC 2, HIPAA, or PCI DSS: use the
  `compliance-audit` skill.
- Erasure in event-sourced or append-only stores: use the
  `event-sourcing-architecture` skill for the crypto-shredding design.
- Schema changes that deletion needs (foreign keys, dropping columns, removing
  a soft-delete pattern): use the `safe-migration` skill.
- Queue mechanics for deletion jobs: use the `background-jobs-and-queues` skill.
- A one-off correction of bad rows: use the `production-data-fix` skill.
- Keeping personal data out of analytics events in the first place: use the
  `product-analytics` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- The retention schedule and records of processing: data classes, periods,
  triggers, legal bases, and exceptions such as financial records. If none
  exists, stop and ask the privacy owner. Never invent a legal period.
- The regimes and response deadlines the owner applies, for example GDPR (Art.
  12(3) sets one month to respond, extendable in some cases) or CCPA.
- How a person maps to records: user ID, email, phone, tenant, device and
  advertising IDs, and hashed identifiers in analytics.
- How requests are authenticated, and who approves manual erasures.
- The processor list with each processor's deletion or privacy API.
- The backup system, its retention window, and the restore runbook.
- Any legal-hold mechanism and who sets and releases holds.

## Workflow

1. **Build the data map from evidence.** Search schemas, ORM models, and
   migrations for personal fields and for foreign keys to user and tenant
   tables. Search connection config, clients, and IaC for every other store:
   replicas, caches, search and vector indexes, object storage, queues and
   their dead-letter queues, warehouse and ETL jobs, logs and their retention
   settings, error tracking, analytics SDKs, email, CRM, support, and payment
   tools. For each store record the fields, the identifier they are keyed by,
   current retention, the deletion mechanism (SQL, API, TTL, or none), and the
   owner. An unknown store is a gap to report, not an assumption to make.
2. **Attach retention rules per data class** from the policy: period, trigger
   (creation, last activity, account closure), action (delete or anonymize),
   and exceptions. Keep the rules as configuration, not scattered constants.
   Record every class the policy does not cover as an open question.
3. **Choose a strategy per store and class.**
   - **Hard delete** is the default for primary records.
   - **Anonymization** is irreversible: remove or coarsen direct and indirect
     identifiers so no combination of fields links back to the person.
     Replacing an email with its hash is not anonymization; low-entropy
     identifiers can be guessed, and a stable hash still links records.
   - **Pseudonymization** swaps identifiers for tokens while a mapping exists.
     It is reversible, the data is still personal data, and it does not
     satisfy erasure on its own.
   - **Crypto-shredding** encrypts a person's data with a per-subject key and
     deletes the key; use it for immutable stores, event logs, and backups.
     Use the `event-sourcing-architecture` skill. Key backups must honor
     deletion too.
   - **Soft-delete flags are not erasure.** A `deleted_at` row is still stored,
     replicated, backed up, and exported. Use soft delete only for a grace
     period set by the policy, followed by a hard delete job.
   - **Records the law requires you to keep** (for example invoices): keep only
     the needed fields, separate them, record the owner's legal basis, and
     restrict access.
4. **Delete from the primary store correctly.** Walk the foreign-key graph from
   the subject and decide per relation: cascade, anonymize, or retain. Shared
   records, such as messages in a group thread, are a product and policy
   decision; ask. Delete in small batches rather than one huge transaction or
   an unbounded `ON DELETE CASCADE` on large tables. Then check for orphans the
   graph misses: denormalized copies (an email on orders), JSON columns, audit
   and history tables, outbox rows and queued payloads, and files referenced by
   deleted rows.
5. **Propagate to every other store.** Write a deletion event in the same
   transaction as the primary delete (an outbox), and give each store an
   idempotent handler: delete search and vector documents by ID (use the
   `build-retrieval` skill for indexes), invalidate cache keys, delete objects
   including noncurrent versions and CDN copies, delete or anonymize warehouse
   raw and derived tables, and call each processor's deletion API. Make sure
   re-index and ETL jobs cannot resurrect data from stale snapshots. Some
   native TTLs delete in the background some time after expiry (DynamoDB TTL,
   for example), so reads that matter should filter expired items.
   Logs usually age out; confirm their retention is set, since some platforms
   keep logs forever by default (CloudWatch Logs log groups do).
6. **Handle backups honestly.** Backups are rarely editable. Choose and
   document one: backups expire within a defined window, isolated and unused
   meanwhile; or a minimal suppression list of erased internal IDs that the
   restore runbook re-applies before restored data goes live. Crypto-shredded
   data stays unreadable in backups. User-facing copy must not promise
   immediate deletion everywhere while backups still hold the data.
7. **Build export (access and portability).** Require a signed-in user with
   recent or step-up authentication; for requests through support, verify
   identity without collecting more data than needed. Assemble from the data
   map, not just the main table: profile, content, activity, files, and the
   derived data the policy includes. Produce machine-readable output (JSON or
   CSV with a documented schema, plus files), excluding other people's personal
   data and security internals such as password hashes. Generate it in a
   background job, store it privately, deliver it through a short-lived
   authorized link, expire it, rate-limit requests per person, and audit each
   export. An export is a full data dump for anyone who takes over the account.
8. **Make jobs idempotent, resumable, and auditable.** Keep an erasure request
   record with per-store state (pending, done, failed, held), attempts, and
   timestamps, saved after each store. Re-running a finished step must succeed
   without effect. Retry with backoff, and alert on requests nearing the policy
   deadline. The audit trail records request ID, requester, approver, times,
   stores completed, and processor request IDs, with minimal personal data and
   its own retention. Every job has a dry-run mode that reports counts per
   store without deleting.
9. **Respect legal holds.** Check holds on the person, tenant, or data class
   before every deletion and every retention purge. Held data is skipped and
   recorded as `held`, never silently dropped; releasing a hold re-queues the
   deletion.
10. **Run retention purges in batches.** Use the period from configuration,
    exclude held data inside the batch selection, prevent overlapping runs, and
    use native TTLs or lifecycle rules where available, after confirming they
    are enabled. A new purge's first production run is a dry run, then one
    approved small batch, then the rest.
11. **Verify the data is gone.** In staging, seed a synthetic person into every
    store, run erasure, then query each store by every identifier (ID, email,
    phone, device ID), and check search results, caches, exports, analytics,
    and files. Automate this as an end-to-end test where possible. In
    production, each job re-queries the stores it touched and records the
    result; processors that delete asynchronously are checked again later.

## Worked example: resumable erasure and a batched purge (illustrative)

A per-store loop that resumes after a crash, skips held stores, defaults to a
dry run, and verifies instead of assuming. Persist `done` after each store.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


class Store(Protocol):
    name: str

    def count(self, subject_id: str) -> int: ...
    def erase(self, subject_id: str) -> None: ...  # must be idempotent


@dataclass
class ErasureRequest:
    id: str
    subject_id: str
    done: set[str] = field(default_factory=set)  # persisted after each store
    held: set[str] = field(default_factory=set)


def run_erasure(req: ErasureRequest, stores: list[Store], held_stores: set[str],
                audit: Callable[[dict], None], dry_run: bool = True) -> dict[str, int]:
    """Erase one subject store by store; safe to re-run after a crash."""
    found_by_store: dict[str, int] = {}
    for store in stores:
        if store.name in req.done:
            continue  # resumed run: this store was finished and verified
        if store.name in held_stores:
            req.held.add(store.name)  # legal hold: skip and record, never drop
            audit({"request": req.id, "store": store.name, "result": "held"})
            continue
        found = store.count(req.subject_id)
        found_by_store[store.name] = found
        if dry_run:
            continue
        if found:
            store.erase(req.subject_id)
        remaining = store.count(req.subject_id)  # verify; do not assume
        if remaining:
            raise RuntimeError(f"{store.name}: {remaining} records remain ({req.id})")
        req.done.add(store.name)
        audit({"request": req.id, "store": store.name, "result": "erased",
               "count": found})
    return found_by_store
```

A PostgreSQL retention batch; the 90-day period stands in for the policy's
value. Holds are excluded inside the batch selection, so a batch of held rows
cannot stall the loop, and `NOT EXISTS` avoids the `NOT IN` trap with nulls.
Repeat until it deletes zero rows.

```sql
-- Dry run first: rows past the period, before excluding held rows.
SELECT count(*) FROM login_events WHERE created_at < now() - interval '90 days';

DELETE FROM login_events                              -- requires approval
WHERE id IN (
  SELECT e.id FROM login_events e
  WHERE e.created_at < now() - interval '90 days'
    AND NOT EXISTS (SELECT 1 FROM legal_holds h
                    WHERE h.user_id = e.user_id AND h.released_at IS NULL)
  ORDER BY e.id
  LIMIT 5000
);
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Enabling self-service deletion, a new purge's first production run, any bulk
  or manual erasure, key destruction, and processor deletion calls each need
  explicit approval after a dry run shows the counts. Mark such lines
  `# requires approval` (`-- requires approval` in SQL).
- Never weaken a test, check, or threshold to make work pass.
- Never invent retention periods, deadlines, or legal exceptions; the privacy
  owner decides, and gaps go in the report as open questions.
- Never report soft deletion, hiding, or hashing as erasure.
- Never copy personal data into tickets, logs, fixtures, or the report; use
  internal IDs. Test with synthetic people only (the
  `synthetic-data-generation` skill can seed them).

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Job tests: a re-run after a simulated crash resumes and finishes, a finished
  step re-runs without effect, held data is skipped and recorded, and a dry run
  deletes nothing.
- End-to-end erasure test in staging: after erasure, searches by every
  identifier in every mapped store return nothing, and another person's data
  is untouched.
- Export tests: a seeded person's export covers every mapped category, another
  user cannot request or download it, the link expires, and the rate limit
  holds.
- Retention tests: dry-run counts match the expected rows, holds are
  respected, and native TTLs and lifecycle rules are confirmed enabled.
- Backups: the restore runbook includes the suppression step, with rehearsal
  evidence if a restore drill was run.
- Type check, lint, and the project's test suite pass.

## Report

- **Data map:** stores, fields, identifiers, deletion mechanism, and owners;
  unknown stores listed as gaps.
- **Policy inputs:** rules applied per data class, their source, and open
  questions for the privacy owner.
- **Strategy:** delete, anonymize, or crypto-shred per store, and what is
  retained under which basis.
- **Propagation and backups:** handlers per store and processor, and the
  backup approach.
- **Export:** authentication, format, delivery, expiry, and rate limit.
- **Jobs:** idempotency, resumption, audit fields, holds, and dry-run results.
- **Approvals:** each production deletion approved, by whom, and when.
- **Verification:** each command and its result.
- **Not verified:** processors with asynchronous deletion, backups not
  restored, and stores not reachable from this environment.

## Optional delegation

The `compliance-auditor` subagent can check the erasure and export paths
against the applicable framework. The `database-architect` subagent can review
the foreign-key graph and retained-record design, and the `migration-planner`
subagent can stage schema changes. The `security-reviewer` subagent can review
the export endpoint, and the `test-writer` subagent can write the end-to-end
erasure test. One agent can complete this workflow alone.
