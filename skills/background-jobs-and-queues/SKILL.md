---
name: background-jobs-and-queues
description: "Add or change background jobs, queue consumers, workers, and scheduled or cron jobs (Sidekiq, Celery, BullMQ, RQ, SQS with Lambda, Kafka consumers, cloud schedulers) with enqueue-after-commit or an outbox, idempotent handlers, bounded retries with jittered backoff, dead-letter queues, concurrency limits, cron overlap and time-zone handling, and graceful shutdown. Use when writing, changing, or debugging a worker, job, consumer, or schedule. Not for vendor API clients (use the third-party-integration skill) or event-sourced stores (use the event-sourcing-architecture skill)."
---

# Background Jobs and Queues

Build jobs, consumers, and schedules that survive duplicates, crashes, deploys,
and bad messages. The stance is **every message can arrive late, twice, or not
at all unless you design against it**: enqueue only committed work, make every
handler safe to repeat, and give every failure a bounded path to a dead-letter
queue that someone watches.

## When to use

- Adding a job, worker, queue consumer, or scheduled task, or changing its
  payload, retries, concurrency, or schedule.
- Jobs that run before their data exists, survive a rolled-back transaction,
  apply twice, block a queue, overlap, pile up, or fire at the wrong hour after a
  daylight-saving change.
- Moving slow work off the request path into a queue.

## When not to use

- The outbound vendor call inside a job (provider timeouts, idempotency keys,
  rate-limit headers): use the `third-party-integration` skill; this skill
  covers the job around the call.
- Event-sourced stores, projections, and outbox relays as the system of record:
  use the `event-sourcing-architecture` skill.
- Batch ETL or warehouse loads: use the `data-pipeline-design` skill.
- Repairing or reprocessing data that a broken job already corrupted: use the
  `production-data-fix` skill.
- A backed-up queue causing an outage now: use the `incident-triage` skill first.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- Queue library and version, broker (Redis, RabbitMQ, SQS, Kafka, or the
  database), and the delivery guarantees it documents. Assume at-least-once;
  ordering usually holds only within one partition, FIFO group, or queue.
- Existing job base classes, retry settings, dead-letter setup, dedupe or
  processed-message tables, outbox, lock helpers, and the scheduler (cron,
  Celery beat, Kubernetes CronJob, EventBridge Scheduler, Cloud Scheduler).
- Worker topology: processes, threads, replicas, autoscaling, shutdown signal,
  grace period, and the database connection pool and server connection limit.
- The job's measured run time (median, p99, maximum) and the third-party rate
  limits it consumes.
- Who owns the queue's alerts, where runbooks live, and how tests run jobs
  (inline or eager mode, a fake queue, or a real broker in a container).

## Workflow

1. **Write the job contract:** trigger, payload, effect, idempotency key,
   ordering needs, latency target, and what happens if it never runs. If loss is
   tolerable (a cache warm-up), say so. If not (a payment, a receipt email),
   step 2 requires a same-database queue or an outbox.
2. **Enqueue only committed work.** A job enqueued inside an open transaction
   can run before commit (the row is not visible yet) or after a rollback (it
   acts on data that never existed).
   - Queue in the same database (a PostgreSQL-backed queue such as Oban, River,
     graphile-worker, or GoodJob, on the application's connection): insert the
     job in the business transaction. This is atomic.
   - Separate broker, loss tolerable: enqueue from an after-commit hook, for
     example Django `transaction.on_commit(...)`, Rails `after_commit` or Active
     Job's after-commit enqueue setting (check your Rails version), or Laravel
     `afterCommit()`. A crash between commit and enqueue still loses the job.
   - Separate broker, loss not acceptable: a transactional outbox. Insert an
     outbox row in the business transaction; a relay publishes rows and marks
     them sent. The relay can publish twice, so consumers deduplicate (step 3).
3. **Make the handler idempotent.** Redelivery after a timeout, a crash before
   acknowledgement, a relay retry, or a manual replay all produce duplicates.
   - Key each job by a stable job or event ID created at enqueue time.
   - For database effects, insert the ID into a processed-messages table with a
     unique constraint in the same transaction as the effect (worked example
     below), or make the effect a conditional update
     (`UPDATE ... WHERE status = 'open'`) or an upsert.
   - For external effects (email, charge, webhook), pass an idempotency key
     derived from the job ID where the provider supports one. Otherwise record
     intent before the call and the outcome after it, and reconcile an unknown
     outcome instead of resending blindly.
   - Enqueue-time uniqueness (BullMQ `jobId`, unique-job plugins) reduces
     duplicates; it does not replace an idempotent handler.
4. **Keep payloads small and stable.** Pass IDs and minimal parameters; the
   handler loads current state and re-checks it, because the order may be
   cancelled by the time the job runs. Put large inputs in object storage and
   pass a reference. Keep secrets and personal data out of payloads: brokers,
   dead sets, dashboards, and logs keep them. During a deploy the new code runs
   jobs the old code enqueued, so add fields as optional, keep old handlers until
   queues drain, and version the payload when its shape changes.
5. **Classify errors and bound retries.** Map driver and client errors to two
   classes in one place.
   - Retryable: timeouts, connection errors, `429`, documented transient `5xx`,
     deadlocks, and serialization failures. Back off exponentially with full
     jitter: a random delay between 0 and min(cap, base times 2 to the power of
     attempt). Set a maximum attempt count from the project's policy; for
     example 8 attempts capped at 10 minutes.
   - Permanent: validation failures, malformed payloads, records that will never
     exist, and most `4xx` other than `408` and `429`. Do not retry; dead-letter
     at once with the reason (for example BullMQ `UnrecoverableError`).
   - Use the library's mechanism: Celery `autoretry_for`, `retry_backoff`,
     `retry_backoff_max`, `retry_jitter`, and `max_retries`; Sidekiq's `retry`
     option and `sidekiq_retries_exhausted`; BullMQ `attempts` and `backoff`;
     SQS `maxReceiveCount` in a redrive policy. Check defaults for your version;
     some retry for days.
6. **Give failures a dead-letter path.** Every queue gets a dead-letter queue
   (or the library's dead or failed set) with retention long enough to
   investigate, an alert when it is non-empty or growing, and a written replay
   procedure: find and fix the cause, replay a sample, then replay the rest at a
   throttled rate through the same idempotent handler. Replays, purges, and
   deleting dead jobs are production actions; ask first. Use the `write-runbook`
   skill for the replay procedure.
7. **Contain poison messages.** A message that crashes or hangs the worker (out
   of memory, a native crash, an infinite loop) may never reach your retry code.
   Count attempts with the broker's delivery count (SQS
   `ApproximateReceiveCount`, RabbitMQ quorum queue delivery limits) rather than
   an in-memory counter, enforce a per-job timeout, and dead-letter after the
   limit. In Kafka a poison record blocks its partition: after the retry budget,
   publish it to a dead-letter topic and commit the offset. For Lambda with SQS
   batches, report partial batch failures (`ReportBatchItemFailures`) so one bad
   message does not retry the whole batch.
8. **Order the timeouts.** If a job outlives its visibility timeout or lock, a
   second worker starts it while the first is still running. Keep the job
   timeout below the SQS visibility timeout, sized from the measured p99 with
   margin, and extend visibility for long jobs (`ChangeMessageVisibility`).
   For Lambda, AWS recommends a queue visibility timeout several times the
   function timeout (check the current docs). Celery on Redis or SQS redelivers
   unacknowledged tasks after its `visibility_timeout`, including ETA and
   countdown tasks scheduled further out. BullMQ marks a job stalled when its
   lock is not renewed, for example when CPU-bound work blocks the event loop.
   In Kafka, one poll's records must finish within `max.poll.interval.ms` or
   the consumer leaves the group.
9. **Limit concurrency and rate.** Total concurrency is processes times
   threads times replicas, and it must fit the database pool and connection
   limit; for example 10 replicas with 25 threads each need 250 connections.
   Separate slow and fast work into different queues so one cannot starve the
   other. Throttle third-party calls with a limiter shared across workers (BullMQ
   `limiter`, a Redis token bucket); Celery's `rate_limit` is per worker
   instance, not global. Cap autoscaling on queue depth at the same ceilings.
10. **Schedule safely.**
    - Prevent overlap with the scheduler's policy (Kubernetes CronJob
      `concurrencyPolicy: Forbid`) or a lock, and skip the run when it is held.
      PostgreSQL `pg_try_advisory_lock` is session-scoped and unsafe behind a
      transaction-mode pooler such as PgBouncer; prefer
      `pg_try_advisory_xact_lock` inside one transaction. A Redis
      `SET key token NX PX ttl` lock needs a TTL longer than the run (or
      renewal), and only the token holder may release it.
    - Run one scheduler instance, or one with leader election; Celery beat or
      cron on every replica fires the job once per replica.
    - Store schedules in UTC, or in an explicit zone when the rule is local.
      Local times between about 01:00 and 03:00 can be skipped or run twice on
      daylight-saving transition days, and schedulers differ; test both
      transition dates for the zones you use.
    - Make each run idempotent per business period ("invoices for 2026-03-08",
      not "everything since the last run"). Choose the missed-run behavior
      (skip, run once, or catch up each period) and configure it (Kubernetes
      `startingDeadlineSeconds`; check your scheduler). Alert when a run does
      not finish on time (a heartbeat or dead man's switch check).
11. **Shut down gracefully.** On `SIGTERM`, stop fetching, finish in-flight jobs
    within the grace period, and let unfinished ones return to the queue:
    acknowledge only after completion (Celery `acks_late`, Kafka offset commits
    after processing). Make the platform's grace period (for example Kubernetes
    `terminationGracePeriodSeconds`) longer than the worker's shutdown timeout.
    Split or checkpoint jobs longer than the grace period so deploys do not kill
    and restart them indefinitely.
12. **Instrument it** with the `observability-setup` skill. Per queue: depth,
    age of the oldest message (SQS `ApproximateAgeOfOldestMessage`, Kafka
    consumer lag), processing time, throughput, failure and retry rates, and
    dead-letter size; per schedule: last success time. Alert on oldest-message
    age and dead-letter growth rather than raw depth. Log job ID, queue, and
    attempt; never log payloads that hold secrets or personal data.
13. **Test the failure paths** listed under Verification.

## Worked example: idempotent consumer (illustrative Python)

The processed-message insert and the effect commit together, so a duplicate
delivery finds the ID and does nothing. `processed_messages` has primary key
`(consumer, message_id)`; prune rows older than the longest redelivery or
replay window.

```python
# Illustrative, psycopg 3. `conn` is opened with autocommit=True, so
# conn.transaction() is the real transaction. `delivery` stands for your
# library's message handle: adapt ack, retry, and dead_letter to it.
from __future__ import annotations

import random

MAX_ATTEMPTS = 8  # use the project's retry policy
BASE_SECONDS, CAP_SECONDS = 2.0, 600.0


class PermanentError(Exception):
    """Retrying cannot help: bad input, a record that will never exist."""


class RetryableError(Exception):
    """Transient: timeout, connection reset, 429, a documented transient 5xx."""


def backoff_seconds(attempt: int) -> float:
    """Full jitter: uniform between 0 and min(cap, base * 2 ** attempt)."""
    return random.uniform(0, min(CAP_SECONDS, BASE_SECONDS * 2 ** attempt))


def mark_invoice_paid(conn, message_id: str, invoice_id: int) -> None:
    with conn.transaction():
        claimed = conn.execute(
            "INSERT INTO processed_messages (consumer, message_id) VALUES (%s, %s) "
            "ON CONFLICT (consumer, message_id) DO NOTHING",
            ("mark-invoice-paid", message_id),
        ).rowcount
        if claimed == 0:
            return  # duplicate delivery: the effect already committed
        row = conn.execute(
            "SELECT status FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,)
        ).fetchone()
        if row is None:
            raise PermanentError(f"invoice {invoice_id} not found")
        if row[0] == "open":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = %s", (invoice_id,))


def handle(conn, delivery) -> None:
    try:
        message_id = str(delivery.body["message_id"])
        invoice_id = int(delivery.body["invoice_id"])
    except (KeyError, TypeError, ValueError):
        delivery.dead_letter(reason="malformed payload")
        return
    try:
        mark_invoice_paid(conn, message_id, invoice_id)
    except PermanentError as exc:
        delivery.dead_letter(reason=str(exc))
    except RetryableError:
        if delivery.attempt >= MAX_ATTEMPTS:
            delivery.dead_letter(reason="retries exhausted")
        else:
            delivery.retry(delay_seconds=backoff_seconds(delivery.attempt))
    else:
        delivery.ack()  # only after the transaction committed
    # Any other exception propagates unacknowledged; the broker redelivers it
    # and its delivery count dead-letters it if it keeps failing.
```

Two concurrent deliveries of one message are safe: the second insert waits on
the unique key, then finds the committed row and skips the effect.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before production queue actions: replaying or purging a dead-letter
  queue, deleting jobs, pausing a queue, changing a live schedule, or scaling
  workers. Purges and deletions cannot be undone.
- Never silence duplicates by disabling retries or redelivery; make the handler
  idempotent instead.
- Never enqueue to a separate broker from inside an open transaction without an
  after-commit hook or an outbox, and never put credentials, tokens, or
  unneeded personal data in job arguments.
- Never raise worker concurrency past the database pool or a provider's limit,
  and never run a scheduler on every web replica.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- **Duplicate delivery:** the same message handled twice, and by two workers at
  once, produces one effect; the second run acknowledges without acting.
- **Retry then success:** a transient failure on the first attempts, then
  success, produces exactly one effect, with delays inside the cap.
- **Permanent failure:** a permanent error or malformed payload goes to the
  dead-letter queue on the first attempt with its reason; a persistent
  transient error goes there after the maximum attempts.
- **Commit boundary:** a rolled-back transaction enqueues nothing, and a
  committed one enqueues exactly one job. Django test cases need
  `captureOnCommitCallbacks(execute=True)`; check how your framework runs commit
  hooks inside test transactions.
- **Compatibility:** a payload in the previous version's shape is still handled.
- **Schedules:** a second run while the first holds the lock skips; jobs
  scheduled in local time behave as intended on both daylight-saving dates.
- **Shutdown:** in a local or staging environment, `SIGTERM` during a job lets it
  finish or returns it to the queue, and it completes once.
- At least one test runs through real serialization and a real or containerized
  broker. Eager or inline modes (Celery `task_always_eager`, Sidekiq inline
  testing) skip serialization, acknowledgement, and redelivery.
- Lint, type check, and the project's test suite pass.

## Report

- **Job contract:** trigger, payload, effect, idempotency key, loss tolerance,
  and enqueue path (same-database insert, after-commit hook, or outbox).
- **Failure handling:** error classes, retry policy, dead-letter queue, alert,
  and where the replay procedure lives.
- **Limits and schedule:** timeouts and visibility, concurrency and pool math,
  rate limits, overlap control, time zone, and missed-run behavior.
- **Shutdown and observability:** grace period, acknowledgement mode, metrics,
  and alerts.
- **Verification:** each test and command with its result.
- **Not verified:** checks that could not run and why (for example no broker in
  CI), and behavior assumed from documentation only.

## Optional delegation

The `resilience-reviewer` subagent can review retries, timeouts, dead-letter
handling, and shutdown; the `concurrency-reviewer` subagent can check locks,
races, and duplicate handling. The `test-writer` subagent can write the
duplicate, retry, and dead-letter tests, and the `backend-builder` subagent can
implement an assigned handler slice. The workflow above stays complete for a
single agent.
