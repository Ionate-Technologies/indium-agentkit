---
name: backend-api
description: "Implement or change server-side endpoints, handlers, and services against an agreed API contract, with boundary validation, server-side authorization, transactional writes, idempotent retries, and tests at the HTTP seam, then produce a verification report. Use when implementing or changing server endpoints. Not for designing a new or breaking contract (use the api-design skill) or schema changes (use the database-design and safe-migration skills)."
---

# Backend API

Implement a server-side change that matches an agreed contract and prove it at
the public seam. The stance is **contract first, server enforced**: the request,
response, and error contract is written down before the handler, and every
request is validated and authorized on the server.

## When to use

- Adding or changing an endpoint, handler, service method, or validation boundary.
- Making an existing write safe to retry, or closing an authorization or
  validation gap in an endpoint.

## When not to use

- There is no contract yet, or the change would break consumers: use the
  `api-design` skill first.
- A schema change or backfill: use the `database-design` skill, then the
  `safe-migration` skill.
- An existing query is slow: use the `query-optimization` skill.
- The endpoint calls a third-party API: use the `third-party-integration` skill
  for that client.
- Contract tests between independently deployed services: use the
  `contract-testing` skill.
- Sign-in, sessions, tokens, or SSO: use the `implement-authentication` skill.
- A permission model or tenant isolation: use the `access-control-design`
  skill.
- Work that should run after the response (emails, webhooks, exports): use the
  `background-jobs-and-queues` skill.
- File uploads and downloads: use the `handle-file-uploads` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The contract: an api-contract handoff, an OpenAPI document, or agreed request,
  response, and error shapes. If none exists, write the minimal contract down
  and confirm it before coding.
- Test, lint, type-check, and build commands from `AGENTS.md`, `CLAUDE.md`,
  package scripts, or the `Makefile`.
- Conventions from two sibling endpoints: routing, validation library, error
  envelope, auth middleware, transaction helper, logging, and test harness.
- The authorization model: the principal, roles, tenant or ownership rules, and
  the authoritative record each check reads.
- Persistence: ORM or query builder, transaction API, isolation level, and any
  approved migration plan.
- Latency and error-rate targets from the project's SLOs. Do not invent them.

## Workflow

1. **Orient.** Read the project instructions and the sibling endpoints; reuse
   their patterns instead of introducing new ones.
2. **Confirm the contract.** Compare it with existing consumers. An additive
   change proceeds. A breaking change stops: explain the break and ask, or route
   to the `api-design` skill.
3. **Trace before editing.** Identify the entry point, middleware chain,
   principal, authorization rule and the record it checks, persistence
   operations, side effects (email, queues, webhooks), and whether a client or
   proxy retry can repeat a write.
4. **Validate at the boundary.** Parse path, query, headers, and body with the
   project's schema library before any business logic. Reject malformed input
   with the project's validation error (often 400 or 422). Use parameter binding
   for every query; never interpolate input into SQL.
5. **Authenticate and authorize on the server.** Return 401 for missing or
   invalid credentials and 403 (or 404, if the contract hides existence) for an
   authenticated caller without access. Check object-level access against the
   authoritative record and tenant, never against client-supplied ids, roles,
   prices, or ownership.
6. **Persist safely.**
   - Wrap multi-write operations in one transaction when a partial write would
     break an invariant.
   - Enforce uniqueness with database constraints and map violations to 409;
     do not check-then-insert.
   - Where concurrent edits are possible, use optimistic concurrency (a version
     column, or `If-Match` with an ETag answered by 412 on mismatch).
   - Make retried creates idempotent with the key pattern below.
   - Perform external side effects after commit, or write them to an outbox
     table in the same transaction.
   - Never change the schema without an approved migration plan, and never add
     hidden schema creation or repair at startup.
7. **Handle errors in one place.** Map known errors to the contract's codes.
   Unknown errors become a generic 500 carrying a request id and are logged on
   the server. Responses never contain stack traces, SQL, or internal ids.
8. **Observe without leaking.** Log decision points with the request id and
   principal id; never log credentials, tokens, session ids, or raw bodies. Add
   metrics or traces where the project already does.
9. **Test at the public seam** with the project's HTTP harness (for example
   Supertest or Playwright request contexts): success, invalid input,
   unauthenticated, forbidden or wrong tenant, not found, conflict, an
   idempotent replay, key reuse with a different body, and any regression. Do
   not mock away the behavior under test, then verify and report as below.

## Reference: typed handler with an idempotency key (illustrative)

Express-style TypeScript with Zod. The interfaces stand in for the project's
framework, data layer, and logger; use the real ones.

```typescript
import { createHash } from 'node:crypto';
import { z } from 'zod';

// Illustrative stand-ins for project types.
interface Actor { id: string; tenantId: string }
interface AuthenticatedRequest {
  requestId: string;
  actor: Actor | null; // set by the auth middleware
  body: unknown;
  header(name: string): string | undefined;
}
interface HttpResponse { status(code: number): HttpResponse; json(body: unknown): void }
interface StoredResponse { status: number; body: unknown }
interface ProjectRow { id: string; name: string; description: string | null; ownerTeamId: string; createdAt: Date }
interface Transaction {
  projects: { insert(row: Omit<ProjectRow, 'id' | 'createdAt'> & { createdBy: string }): Promise<ProjectRow> };
  auditLog: { insert(entry: { actorId: string; action: string; entityId: string; requestId: string }): Promise<void> };
  idempotencyKeys: {
    // INSERT ... ON CONFLICT (scope, key) DO NOTHING; true when this call inserted the row.
    insertIfAbsent(row: { scope: string; key: string; requestHash: string }): Promise<boolean>;
    find(scope: string, key: string): Promise<{ requestHash: string; response: StoredResponse | null }>;
    saveResponse(scope: string, key: string, response: StoredResponse): Promise<void>;
  };
}
interface Database {
  teams: { userHasRole(teamId: string, userId: string, roles: string[]): Promise<boolean> };
  transaction<T>(fn: (trx: Transaction) => Promise<T>): Promise<T>;
}
interface Logger { info(event: string, fields: Record<string, unknown>): void }

// Error-handling middleware maps this to the project's error envelope.
class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fieldErrors?: Record<string, string[] | undefined>,
  ) {
    super(message);
  }
}

const CreateProjectBody = z.object({
  name: z.string().min(1).max(120),
  description: z.string().max(2000).optional(),
  ownerTeamId: z.string().uuid(),
});

// Store key, request hash, and response with the business write, in the same
// transaction. In PostgreSQL under READ COMMITTED, a concurrent insert of the
// same key waits for this transaction, then sees the committed row.
async function runIdempotent(
  trx: Transaction,
  scope: string,
  key: string,
  input: unknown,
  execute: () => Promise<StoredResponse>,
): Promise<StoredResponse> {
  // Use a canonical (stable key order) serialization in real code.
  const requestHash = createHash('sha256').update(JSON.stringify(input)).digest('hex');
  if (!(await trx.idempotencyKeys.insertIfAbsent({ scope, key, requestHash }))) {
    const prior = await trx.idempotencyKeys.find(scope, key);
    if (prior.requestHash !== requestHash) {
      throw new ApiError(422, 'IDEMPOTENCY_KEY_REUSED', 'This Idempotency-Key was used with a different request.');
    }
    if (prior.response === null) {
      // Only reachable if keys are claimed outside the business transaction.
      throw new ApiError(409, 'REQUEST_IN_PROGRESS', 'The original request is still in progress.');
    }
    return prior.response; // replay: same status and body, no second write
  }
  const response = await execute();
  await trx.idempotencyKeys.saveResponse(scope, key, response);
  return response;
}

export async function createProject(req: AuthenticatedRequest, res: HttpResponse, db: Database, log: Logger): Promise<void> {
  const actor = req.actor;
  if (!actor) throw new ApiError(401, 'UNAUTHENTICATED', 'Authentication is required.');

  const parsed = CreateProjectBody.safeParse(req.body);
  if (!parsed.success) {
    // Zod 3 API; Zod 4 also provides z.flattenError(parsed.error).
    throw new ApiError(422, 'VALIDATION_FAILED', 'Request body is invalid.', parsed.error.flatten().fieldErrors);
  }
  const input = parsed.data;

  const key = req.header('Idempotency-Key');
  if (!key || key.length > 128) {
    throw new ApiError(400, 'IDEMPOTENCY_KEY_INVALID', 'An Idempotency-Key header of at most 128 characters is required.');
  }

  // Authorize against the authoritative team record, never a client-supplied role.
  if (!(await db.teams.userHasRole(input.ownerTeamId, actor.id, ['owner', 'maintainer']))) {
    throw new ApiError(403, 'FORBIDDEN', 'You cannot create projects for this team.');
  }

  const result = await db.transaction((trx) =>
    runIdempotent(trx, `${actor.tenantId}:${actor.id}`, key, input, async () => {
      const row = await trx.projects.insert({
        name: input.name,
        description: input.description ?? null,
        ownerTeamId: input.ownerTeamId,
        createdBy: actor.id,
      });
      await trx.auditLog.insert({ actorId: actor.id, action: 'project.created', entityId: row.id, requestId: req.requestId });
      const data = { ...row, createdAt: row.createdAt.toISOString() };
      return { status: 201, body: { data } };
    }),
  );

  log.info('project.create', { requestId: req.requestId, actorId: actor.id, status: result.status });
  res.status(result.status).json(result.body);
}
```

Points that carry over to any stack: scope keys to the caller so one client
cannot replay another's response; expire keys after the contract's retention
window; a thrown error rolls back the key with the write, so a failed request
can be retried with the same key.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Never run migrations, seed scripts, or test traffic against shared or
  production environments.
- Never weaken a test, check, or threshold to make work pass, and never update
  a test to match an incorrect implementation.
- Authorization lives on the server; a hidden UI control is not a control.
- Do not invent response fields or error semantics; reuse the shared types and
  envelope. Keep unrelated refactors out of a behavior change.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Type check, lint, the focused endpoint tests, then the full suite all pass.
- The seam tests cover every row of the contract's error matrix that the change
  touches, including an idempotent replay if the operation takes a key.
- `git diff` contains no secrets, debug output, generated artifacts, or edits
  outside the change.
- If the endpoint is on a path with a project SLO, measure against it or state
  that it was not measured.

## Report

- **Endpoints:** each operation changed and its contract status (unchanged,
  additive, breaking-approved).
- **Security:** authentication, authorization, and validation evidence.
- **Data effects:** tables written, transactions, idempotency, migration dependency.
- **Not verified:** checks that could not run and why.

Save the verification report where the project keeps such documents (for
example `docs/`), or include it in the pull request description.

<!-- handoff: verification-report -->
```markdown
# Verification report: endpoint or change name

## Scope

The change, environment, revision, and the contract it was verified against.

## Commands and results

| Command | Result | Notes |
| --- | --- | --- |
| project type check | pass, fail, or not run | Relevant output summary. |

## Evidence

Seam tests per contract case, and logs or manual steps without sensitive data.

## Limitations

Checks that could not run, assumptions, and unmeasured SLOs.

## Handoff

**Changed contract:** Observable behavior added or changed, or none.

**Files / systems affected:** Handlers, services, tables, and consumers.

**Evidence and tests:** Completed checks and their outcome.

**Risks / rollback:** Known risks and the recovery path.

**What the next agent needs:** Blockers, deployment notes, and follow-up.
```

## Optional delegation

- The `backend-builder` subagent can implement a bounded slice inside assigned
  paths; review its diff and rerun the checks yourself.
- The `security-reviewer` subagent can independently review authorization and
  validation; the `test-writer` subagent can add seam tests.
