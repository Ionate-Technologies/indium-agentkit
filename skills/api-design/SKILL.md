---
name: api-design
description: "Design an API contract (resources, operations, request and response schemas, errors, authorization, pagination, idempotency, and versioning) from requirements before implementation, and produce an api-contract handoff. Use when a feature needs new or changed endpoints, an OpenAPI document, or a compatibility decision. Design only; not for implementing endpoints (use the backend-api skill)."
---

# API Design

Turn requirements into an implementation-ready API contract that an implementer
can build without making further design decisions. The stance is **design only,
conventions first**: inherit the project's envelope, error shape, naming, and
versioning, and record every unresolved question instead of inventing an answer.

## When to use

- A feature needs new resources or operations, or changes to existing ones.
- Someone asks for an OpenAPI (or GraphQL or protobuf) contract, an error
  matrix, or a pagination or idempotency decision.
- A proposed change may break existing consumers and needs a compatibility verdict.

## When not to use

- The contract is agreed and the task is to build it: use the `backend-api` skill.
- The question is tables, constraints, or indexes: use the `database-design` skill.
- A breaking change must be rolled out across deployed consumers: delegate the
  rollout plan to the `migration-planner` subagent.
- Consumer-driven contract tests between services: use the `contract-testing` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the contract.

- Requirements: the feature brief, ticket, or request, and who calls the API
  (browser, mobile app, partner, internal service).
- Conventions from at least two sibling routes, OpenAPI documents, or shared
  schema types: envelope, error shape, field casing, pluralization, versioning,
  pagination, and auth scheme.
- The data model and the ownership rules (user, team, tenant) that authorization
  depends on.
- The currently published contract, if any, to compare changes against.
- Where the project keeps contracts (for example `openapi/` or `docs/api/`) and
  any contract lint or diff tooling it already uses.

## Workflow

1. **State assumptions first.** List the requirements you are designing for and
   every gap or assumption. Ambiguities become open questions in the handoff;
   never resolve them by invention.
2. **Model resources.** Name resources, relationships, ownership, and lifecycle
   states with the existing naming conventions. Embed children the client always
   needs; link or reference by id anything large or independently paginated.
   Check that new paths do not collide with existing routes.
3. **Design operations.** For each: method, path, purpose, caller, side effects,
   and idempotency.
   - GET, PUT, and DELETE must be idempotent by design.
   - POST creates that clients may retry take an `Idempotency-Key` header.
     Specify the key's scope (per caller or tenant), its retention window, and
     replay behavior: the same status and body for a repeat, 422 when the key is
     reused with a different body, and 409 while the original is still in
     progress (the IETF Idempotency-Key draft's choices; follow the project if
     it already decided otherwise).
   - Map domain actions that are not CRUD to explicit sub-resources
     (`POST /invoices/{id}/payment-retries`) rather than overloading PATCH.
4. **Specify requests.** Types, required versus optional, formats (`uuid`,
   `date-time`), bounds, enums, and patterns. Mark each field create-only,
   updatable, or read-only. Reuse shared types and say which ones.
5. **Specify responses and pagination.** Envelope, always-present versus
   optional fields, and nullability. In OpenAPI 3.1 write `type: [string, "null"]`;
   the 3.0 keyword `nullable` was removed. For lists, choose cursor or offset,
   name the fields, take the default and maximum page size from project
   convention, and require a stable sort order. State cache semantics (`ETag`,
   `Cache-Control`) where they matter.
6. **Define the error matrix.** Per operation, list which of 400 or 422
   (validation), 401, 403, 404, 409, 412 (failed precondition), and 429 apply,
   each with a stable machine-readable code and a safe message. Reuse the
   existing error envelope exactly. Decide whether a caller who may not see an
   object gets 403 or 404, so existence does not leak.
7. **Attach authorization to every operation.** State the authentication
   requirement and the server-side rule (ownership, role, tenant scope) checked
   against an authoritative record. An operation without one is incomplete.
8. **Decide compatibility** against the published contract.
   - Breaking: removing or renaming a field or operation; changing a type or
     meaning; making an optional request field required; tightening validation;
     making a response field optional or nullable; changing status or error codes.
   - Usually compatible: adding an optional request field, a new operation, or a
     new response field. Adding a response enum value breaks clients that switch
     exhaustively unless the contract tells clients to tolerate unknown values;
     say which applies.
   - For a breaking change, propose a new version or a deprecation path
     (changelog, `Deprecation` and `Sunset` headers, an overlap window).
9. **Trace requirements.** Every requirement maps to at least one operation and
   every operation to a requirement; anything left over is scope creep or a
   missing requirement.
10. **Write the contract and handoff** in the project's contract location.

## Reference: OpenAPI 3.1 fragment (illustrative)

The depth expected for one resource: a paginated list, an idempotent create, a
nullable field, and the shared error envelope.

```yaml
openapi: 3.1.0
info: { title: Billing API, version: "1.0.0" }
paths:
  /v1/invoices:
    get:
      operationId: listInvoices
      parameters:
        - { name: cursor, in: query, schema: { type: string } }
        - { name: limit, in: query, schema: { type: integer, minimum: 1, maximum: 100, default: 25 } }
      responses:
        "200":
          description: Invoices for the caller's tenant, newest first.
          content:
            application/json:
              schema:
                type: object
                required: [data, pagination]
                properties:
                  data: { type: array, items: { $ref: "#/components/schemas/Invoice" } }
                  pagination: { $ref: "#/components/schemas/CursorPage" }
        "401": { $ref: "#/components/responses/Error" }
    post:
      operationId: createInvoice
      parameters:
        - { name: Idempotency-Key, in: header, required: true, schema: { type: string, maxLength: 128 } }
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/CreateInvoiceRequest" }
      responses:
        "201":
          description: Created. A replay with the same key returns the original response.
          content:
            application/json:
              schema:
                type: object
                required: [data]
                properties: { data: { $ref: "#/components/schemas/Invoice" } }
        "409": { $ref: "#/components/responses/Error" }
        "422": { $ref: "#/components/responses/Error" }
components:
  schemas:
    Invoice:
      type: object
      required: [id, status, currency, amountDueCents, dueAt, createdAt]
      properties:
        id: { type: string, format: uuid, readOnly: true }
        status: { type: string, enum: [draft, open, paid, void] }
        currency: { type: string, pattern: "^[A-Z]{3}$" }
        amountDueCents: { type: integer, minimum: 0 }
        dueAt: { type: [string, "null"], format: date-time }
        createdAt: { type: string, format: date-time, readOnly: true }
    CreateInvoiceRequest:
      type: object
      required: [currency, amountDueCents]
      properties:
        currency: { type: string, pattern: "^[A-Z]{3}$" }
        amountDueCents: { type: integer, minimum: 1 }
        dueAt: { type: string, format: date-time }
    CursorPage:
      type: object
      required: [hasMore, nextCursor]
      properties:
        hasMore: { type: boolean }
        nextCursor: { type: [string, "null"] }
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code, message]
          properties:
            code: { type: string }
            message: { type: string }
            fieldErrors: { type: object, additionalProperties: { type: array, items: { type: string } } }
  responses:
    Error:
      description: Error in the shared envelope.
      content:
        application/json:
          schema: { $ref: "#/components/schemas/ErrorEnvelope" }
```

In a real contract each status gets its own described response and error codes;
the single `Error` response here only keeps the fragment short.

## Guardrails

- Design only: do not implement handlers, persistence, or migrations here.
- Do not introduce a new envelope, error shape, naming scheme, or versioning
  scheme when the project has one; justify any divergence in the handoff.
- Do not invent authorization rules, business rules, or limits the requirements
  do not state; record them as assumptions or open questions.
- Examples use obvious placeholders; never real tokens, internal hostnames, or
  personal data. Error responses never promise stack traces, SQL, or internal ids.
- Revert or delete only files you created or changed in this session.
- Ask before publishing a contract to a shared registry, developer portal, or
  external partner.

## Verification

Use the project's contract tooling where it exists, and run each check separately.

- The document parses and passes the project's contract lint. If none is
  configured and Spectral is installed, run `npx --no-install spectral lint
  openapi/billing.yaml`; Spectral needs a ruleset, for example a
  `.spectral.yaml` containing `extends: ["spectral:oas"]`.
- Compatibility: if `oasdiff` is installed, `oasdiff breaking
  openapi/billing.published.yaml openapi/billing.yaml` lists breaking changes
  (see `oasdiff breaking --help` for the fail-on option in your version).
  Otherwise walk the breaking-change list in step 8 by hand and say so.
- If client or server types are generated from the contract, regenerate them and
  run the project's type check.
- Every operation has an authorization rule and an error matrix, and every
  requirement traces to an operation.

## Report

- **Contract:** its path, and the operation inventory.
- **Decisions:** envelope, pagination, idempotency, shared types reused.
- **Compatibility verdict:** additive or breaking, with the evidence.
- **Open questions:** each one, and who must answer it.
- **Not verified:** checks that could not run and why.

Save the handoff where the project keeps design documents (for example
`docs/api/`, next to the OpenAPI file).

<!-- handoff: api-contract -->
```markdown
# API contract: feature or resource name

## Resources and operations

Method, path, purpose, caller, and idempotency for each operation.

## Authentication and authorization

Identity requirement and the server-side ownership, role, or tenant rule per operation.

## Requests and responses

Typed fields, validation, mutability, envelope, pagination, and placeholder-only examples.

## Errors

Status codes, stable error codes, safe messages, and the expected client action.

## Compatibility

Versioning, deprecation, breaking-change verdict, and rollout impact.

## Handoff

**Changed contract:** New, changed, or removed public behavior.

**Files / systems affected:** Contract files, consumers, services, and docs.

**Evidence and tests:** Lint and compatibility results, and the requirement trace.

**Risks / rollback:** Compatibility risks and the recovery path.

**What the next agent needs:** Implementation decisions and open questions.
```

## Optional delegation

- Delegate an independent review of the draft contract to the `api-designer`
  subagent; re-check any finding against the requirements before acting on it.
- Once the contract is approved, the `backend-builder` subagent can implement
  it following the `backend-api` skill.
- Data model questions can go to the `database-architect` subagent.
