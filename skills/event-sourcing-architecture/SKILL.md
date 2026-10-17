---
name: event-sourcing-architecture
description: "Design event-sourced systems and CQRS read models: aggregates and events, an append-only store with optimistic concurrency, outbox publishing to idempotent consumers, projections with persisted checkpoints, snapshots, event versioning and upcasting, and erasure of personal data. Use when a domain needs the full history of state changes, temporal queries, or several read models built from one write model. Not for ordinary CRUD or simple audit trails (use the database-design skill)."
---

# Event Sourcing Architecture

Design systems whose state is derived by folding an append-only log of domain
events, with read models built as projections of that log. The stance is
**question the fit first, then make every reader replay-safe**: projections,
relays, and consumers must tolerate duplicates, retries, and rebuilds without
losing or double-applying an event.

## When to use

- The business needs the history of how state changed, not only the current
  state: ledgers, order or claim lifecycles, regulated workflows.
- Temporal questions ("what did we know at time T") or replaying history into
  new read models.
- Several differently shaped read models from one write model (CQRS), or
  integration events for other services.

## When not to use

- Most CRUD applications. Event sourcing adds event versioning, projection lag,
  rebuilds, and harder erasure. If the need is an audit trail, an audit table or
  change data capture on a normal schema is usually enough: use the
  `database-design` skill.
- Analytics over events: use the `data-pipeline-design` skill.
- Moving an existing table-backed system onto events: plan the move with the
  `safe-migration` skill.
- Independent review of the store schema and access paths: delegate to the
  `database-architect` subagent.

## Inputs to gather

Discover these before asking. Ask only about what remains ambiguous.

- The requirement that needs history or replay. If nobody can name one, say so
  and recommend a conventional schema.
- Domain: aggregates (consistency boundaries), commands, the invariants each
  command enforces, and expected events per aggregate.
- Store and broker: a PostgreSQL table, EventStoreDB, DynamoDB, Kafka, or other,
  and whether the store provides a commit-ordered global position.
- Read models, their consumers, and acceptable projection lag.
- Personal data that events would carry, and the retention and erasure duties.
- The project's test runner and commands.

## Workflow

1. **Decide whether it fits.** Write down the requirement that needs history.
   If there is none, stop and recommend a conventional design.
2. **Model aggregates and events.** One aggregate is one consistency boundary
   and one stream. Events are past-tense business facts (`OrderPaid`, not
   `SetStatus`) that carry only what happened. Command handlers enforce
   invariants before appending. The fold (`evolve`) never rejects a stored
   event, and it handles every event type the stream can contain.
3. **Define the envelope:** `eventId` (unique, for deduplication), `streamId`,
   `streamVersion` (1..n within the stream), a store-wide position, `type`,
   `schemaVersion`, `occurredAt`, `data`, and metadata (correlation id,
   causation id, actor).
4. **Append with optimistic concurrency.** The handler loads the stream at
   version N and appends N+1 onward. A unique `(stream_id, stream_version)`
   constraint rejects a concurrent writer; reload and re-run the command, or
   return a conflict. Never overwrite.
5. **Publish through an outbox.** Write events and outbox rows in one
   transaction, or treat the events table itself as the outbox. A relay
   publishes in order and records its progress. It can crash after publishing
   and before recording, so delivery is at-least-once: every consumer
   deduplicates by `eventId`, recording processed ids in the same transaction
   as its side effect.
6. **Build projections with persisted checkpoints.** A projection stores its
   checkpoint in the same transaction as its read-model write: either the last
   applied `streamVersion` per stream, or one global position (see the caveat
   below). A duplicate is skipped; a gap is an error to retry, never a skip.
   Deliver one stream's events to one worker at a time (partition by stream id).
7. **Plan rebuilds.** A projection is disposable. Build a new version from the
   start of the log beside the old one, switch reads once it catches up, then
   retire the old one (dropping tables in shared environments needs approval).
8. **Version events** and **snapshot only when needed** (sections below).
9. **Handle personal data and corrections** (sections below) before the first
   event is stored; both are expensive to retrofit.

## Global position caveat

A checkpoint on a global position only works if positions become visible in
order. A PostgreSQL identity or sequence value is assigned at insert, not at
commit, so a reader can see position 11 before 10 commits, advance past 10,
and never apply it. Choose one:

- Per-stream checkpoints, as in the example below.
- Serialize appends (for example a transaction-level advisory lock) and accept
  the throughput limit.
- Store the writing transaction id with each event (`pg_current_xact_id()`,
  PostgreSQL 13+) and read only events whose transaction id is below
  `pg_snapshot_xmin(pg_current_snapshot())`, so no in-flight transaction can
  still commit a lower position.
- A purpose-built store whose position is commit-ordered; confirm this in its
  documentation.

## Reference example

Illustrative PostgreSQL store:

```sql
CREATE TABLE events (
    global_position bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stream_id       text        NOT NULL,
    stream_version  integer     NOT NULL CHECK (stream_version > 0),
    event_id        uuid        NOT NULL UNIQUE,
    event_type      text        NOT NULL,
    schema_version  integer     NOT NULL,
    data            jsonb       NOT NULL,
    metadata        jsonb       NOT NULL DEFAULT '{}',
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    -- Optimistic concurrency: two writers cannot both append version N.
    UNIQUE (stream_id, stream_version)
);

-- Append-only by privilege, not convention. The application role must not
-- own the table.
REVOKE UPDATE, DELETE, TRUNCATE ON events FROM app_writer;
GRANT SELECT, INSERT ON events TO app_writer;

CREATE TABLE projection_checkpoints (
    projection   text    NOT NULL,
    stream_id    text    NOT NULL,
    last_version integer NOT NULL,
    PRIMARY KEY (projection, stream_id)
);
```

Illustrative TypeScript domain model, a pure fold, and a command handler:

```typescript
export type OrderEvent =
  | { type: 'OrderCreated'; data: { customerId: string; totalCents: number } }
  | { type: 'OrderPaid'; data: { paymentId: string } }
  | { type: 'OrderShipped'; data: { trackingNumber: string } }
  | { type: 'OrderCancelled'; data: { reason: string } };

export interface Envelope {
  eventId: string;
  streamId: string;
  streamVersion: number;
  schemaVersion: number;
  occurredAt: string;
}

export type StoredOrderEvent = Envelope & OrderEvent;

export interface OrderState {
  status: 'NONE' | 'CREATED' | 'PAID' | 'SHIPPED' | 'CANCELLED';
  customerId?: string;
  totalCents: number;
  version: number; // streamVersion of the last applied event
}

export const initialOrder: OrderState = { status: 'NONE', totalCents: 0, version: 0 };

// Pure: no I/O, no clock, never rejects a stored event.
export function evolve(state: OrderState, e: StoredOrderEvent): OrderState {
  const version = e.streamVersion;
  switch (e.type) {
    case 'OrderCreated':
      return { status: 'CREATED', customerId: e.data.customerId, totalCents: e.data.totalCents, version };
    case 'OrderPaid':
      return { ...state, status: 'PAID', version };
    case 'OrderShipped':
      return { ...state, status: 'SHIPPED', version };
    case 'OrderCancelled':
      return { ...state, status: 'CANCELLED', version };
    default: {
      const unhandled: never = e; // compile error if an event type is missing
      throw new Error(`unhandled event: ${JSON.stringify(unhandled)}`);
    }
  }
}

export const rehydrate = (events: StoredOrderEvent[], from: OrderState = initialOrder): OrderState =>
  events.reduce(evolve, from);

// Invariants live in command handlers, before anything is appended.
export function decideShip(state: OrderState, trackingNumber: string): OrderEvent[] {
  if (state.status !== 'PAID') {
    throw new Error(`cannot ship an order in status ${state.status}`);
  }
  return [{ type: 'OrderShipped', data: { trackingNumber } }];
}
```

Idempotent projection. The checkpoint is per stream and commits with the
read-model write, so a crash between them can neither skip an event nor apply
it twice, and events from different orders never shadow each other:

```typescript
// Adapt this minimal interface to the project's database client.
export interface Tx {
  query<R>(sql: string, params: unknown[]): Promise<{ rows: R[] }>;
}
export interface Db {
  transaction<T>(work: (tx: Tx) => Promise<T>): Promise<T>;
}

const PROJECTION = 'order_view';
const STATUS = { OrderPaid: 'PAID', OrderShipped: 'SHIPPED', OrderCancelled: 'CANCELLED' } as const;

export async function projectOrderEvent(db: Db, e: StoredOrderEvent): Promise<void> {
  await db.transaction(async (tx) => {
    const { rows } = await tx.query<{ last_version: number }>(
      `SELECT last_version FROM projection_checkpoints
        WHERE projection = $1 AND stream_id = $2
        FOR UPDATE`,
      [PROJECTION, e.streamId],
    );
    const last = rows[0]?.last_version ?? 0;
    if (e.streamVersion <= last) return; // duplicate delivery or replay
    if (e.streamVersion !== last + 1) {
      // An earlier event has not arrived yet: fail so delivery is retried.
      throw new Error(`gap in ${e.streamId}: expected ${last + 1}, got ${e.streamVersion}`);
    }

    switch (e.type) {
      case 'OrderCreated':
        await tx.query(
          `INSERT INTO order_view (order_id, customer_id, total_cents, status)
           VALUES ($1, $2, $3, 'CREATED')`,
          [e.streamId, e.data.customerId, e.data.totalCents],
        );
        break;
      case 'OrderPaid':
      case 'OrderShipped':
      case 'OrderCancelled':
        await tx.query(`UPDATE order_view SET status = $2 WHERE order_id = $1`, [e.streamId, STATUS[e.type]]);
        break;
    }

    await tx.query(
      `INSERT INTO projection_checkpoints (projection, stream_id, last_version)
       VALUES ($1, $2, $3)
       ON CONFLICT (projection, stream_id) DO UPDATE SET last_version = EXCLUDED.last_version`,
      [PROJECTION, e.streamId, e.streamVersion],
    );
  });
}
```

If two deliveries of a stream's first event race, the primary key on
`order_view` rejects one; its retry then sees the checkpoint and skips.

## Event versioning and upcasting

- Never change the meaning of a stored event. A new optional field is an
  additive change: bump `schemaVersion` and default the field when reading.
- For renames, unit changes, or splits, write an upcaster that converts old
  payloads to the current shape on read. Chain them (v1 to v2 to v3), keep them
  pure, and test each against stored fixtures of the old version.
- A change in business meaning is a new event type, not a new version.
- Do not rewrite the log in place. If the log itself must be transformed, copy
  it to a new store and switch over with the `safe-migration` skill.

```typescript
// Illustrative: v1 OrderCreated stored `customer`; v2 renamed it to `customerId`.
interface RawEvent { type: string; schemaVersion: number; data: Record<string, unknown> }

export function upcast(e: RawEvent): RawEvent {
  if (e.type === 'OrderCreated' && e.schemaVersion === 1) {
    const { customer, ...rest } = e.data;
    return { ...e, schemaVersion: 2, data: { ...rest, customerId: customer } };
  }
  return e;
}
```

## Snapshots

- A snapshot is a cache: `(stream_id, stream_version, snapshot_schema_version,
  state)`. Load the latest one and replay only the events after its version.
- Version snapshots separately from events. When the state shape or the fold
  logic changes, bump the snapshot schema version and ignore older snapshots
  (replay from events) until new ones are written. Snapshots can be deleted and
  rebuilt at any time.
- Add them only when measured replay time is a problem. Very long streams often
  mean the aggregate boundary is too wide.

## Personal data and erasure

Events are immutable, so a person's data cannot be removed from them with
`UPDATE` or `DELETE`. Decide before storing any:

- **Keep personal data out of events.** Store it in a separate mutable store
  keyed by subject id; events carry only the id.
- **Crypto-shredding.** Encrypt personal fields with a per-subject key held in
  a key store (KMS or vault). Erasure deletes the key, leaving the ciphertext
  unreadable. Projections must handle a missing key by rendering the value as
  redacted. Read models, caches, and search indexes that hold plaintext must be
  erased separately, and key-store backups need a retention that honors erasure.

Confirm with the project's privacy or legal owner that the chosen approach
meets its erasure obligations.

## Corrections without mutation

If a request asks to `UPDATE` or `DELETE` stored events, explain why not:
projections, consumers, and audits rely on the log as the source of truth, and
silently rewritten history breaks replay. Propose a compensating event instead
(`OrderCancelled`, `PaymentRefunded`, or an explicit correction such as
`OrderAmountCorrected`) that projections apply like any other event.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including projection rebuilds or replays against shared environments.
- Never weaken a test, check, or threshold to make work pass.
- Never update or delete stored events; corrections are new events.
- Every append carries an expected version; every consumer deduplicates by
  `eventId`; every checkpoint commits with its read-model write.
- Folds and upcasters are pure: no network, disk, clock, or randomness.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Command handlers: given past events, a command yields the expected new events
  or the expected rejection (for example shipping an unpaid order fails).
- Replay determinism: folding the same events twice yields equal state, and a
  snapshot plus the remaining events equals a full replay.
- Projection idempotency: delivering every event twice, and interleaving
  several streams, yields the same read model as a single clean pass; a gap
  raises an error instead of advancing the checkpoint.
- Concurrency: two appends at the same expected version produce exactly one
  success and one conflict, against a real database.
- Upcasters: each stored old-version fixture upcasts to the current shape.
- Erasure: after deleting a subject's key, no read model or index still shows
  that subject's plaintext.

## Report

- **Fit:** the requirement that justifies event sourcing, or the recommendation
  against it.
- **Model:** aggregates, event types with schema versions, and command invariants.
- **Store:** engine, concurrency mechanism, position and checkpoint strategy.
- **Publishing and projections:** outbox relay, consumer deduplication, rebuild
  plan, expected lag.
- **Versioning, snapshots, and erasure:** the approach chosen for each.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `database-architect` subagent can review the store schema, constraints, and
indexes, and the `test-writer` subagent can write the replay, idempotency, and
concurrency tests. One agent can complete this workflow alone.
