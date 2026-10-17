---
name: contract-testing
description: "Write consumer-driven contract tests with Pact (consumer tests, provider verification with state handlers, broker publishing, and can-i-deploy gates) and keep frontend mocks aligned, so interface breaks between services or between frontend and backend fail in CI instead of production. Use when adding or changing an interface between independently deployed services or apps. Not for designing the API itself (use the api-design skill)."
---

# Contract Testing

Catch interface breaks between independently deployed consumers and providers
without a full end-to-end environment. The stance is **consumer perspective,
interface shape only**: contracts record what the consumer actually sends and
reads, and they verify structure, not business logic.

## When to use

- A consumer (web app, mobile app, service) and a provider deploy independently
  and a change to either could break the other.
- Adding a new interaction, error case, or field that crosses such a boundary.
- Wiring provider verification, broker publishing, or `can-i-deploy` into CI.

## When not to use

- Designing or changing the API contract itself: use the `api-design` skill.
- Implementing the provider endpoint: use the `backend-api` skill.
- A third-party API you do not control cannot run provider verification: use
  the `third-party-integration` skill and test against recorded or documented
  responses.
- A contract test that passes and fails on the same code: use the
  `flaky-test-triage` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The boundary: which side calls, which side owns the interface, and the
  participant names a Pact Broker already knows.
- The API contract (OpenAPI, GraphQL schema, protobuf) and the consumer's client
  modules that cross the boundary.
- Existing contract tooling: `@pact-foundation/pact` version, `pacts/`
  directories, MSW handlers, fixture factories, and the error envelope.
- How the provider starts in tests and seeds its own test database.
- CI: where consumer tests run, whether a broker exists, and how secrets reach jobs.
- Test commands from `AGENTS.md`, package scripts, or the `Makefile`.

## Workflow

1. **Inventory consumer calls.** List every client function that crosses the
   boundary. Each gets at least one success interaction and one error-envelope
   interaction (for example 404 or 422).
2. **Write consumer interactions from the consumer's side.** Include only the
   request fields the consumer sends and the response fields it reads. Give each
   interaction a provider state (`invoice inv_42 exists`) so the provider can
   arrange data deterministically.
3. **Use matchers for dynamic values.** Ids, timestamps, tokens, and generated
   values use type or regex matchers. Exact literals are for values the consumer
   genuinely pins, such as enum-like error codes.
4. **Drive the real client.** Point the consumer's actual client code at the
   Pact mock server; never assert the mock against itself.
5. **Check the generated pact files.** They are generated output: regenerate,
   never hand-edit. Run the suite twice and confirm the files are identical (see
   Verification).
6. **Verify the provider in isolation.** Replay pacts against a local or
   ephemeral provider instance with its own test database. Implement a state
   handler for every provider state any consumer uses. Inject test credentials
   with a request filter. Never target production.
7. **Select pacts by branch and environment.** Use
   `consumerVersionSelectors` such as `{ mainBranch: true }`,
   `{ deployedOrReleased: true }`, and `{ matchingBranch: true }`. The tag-based
   forms (`{ tag: 'main', latest: true }`, `--tag`) are the older API; use them
   only if the broker is too old for branches and environments. Turn on pending
   pacts (`enablePending`) so a new consumer expectation does not break the
   provider's main build before it is implemented.
8. **Publish and gate in CI.** Consumers publish pacts with `--branch` and their
   version. Providers verify on their own pull requests, and the broker can
   trigger verification when a changed pact is published. Before deploying, run
   `can-i-deploy`; after a deployment succeeds, record it with
   `record-deployment` (or `record-release` for mobile apps and libraries).
   Without a broker, the provider can verify pact files from a shared artifact
   (the `pactUrls` option), but there is no `can-i-deploy` gate.
9. **Align frontend mocks.** MSW handlers and similar mocks are not verified
   against the provider. Reuse the pact's example payloads or generate both from
   the same fixtures so mock drift shows up in review.

## Reference: consumer test and provider verification (illustrative)

pact-js with Vitest. Recent pact-js versions also export `PactV4`, which uses a
builder-style `addInteraction()` API; use PactV3 or PactV4 per your installed
version. In MatchersV3, `regex` takes the pattern first and the example second.

```typescript
import { PactV3, MatchersV3 } from '@pact-foundation/pact';
import { describe, it, expect } from 'vitest';
import { fetchInvoice } from '../src/clients/invoiceClient';

const { like, eachLike, string, regex, uuid, decimal, integer } = MatchersV3;
const pact = new PactV3({ consumer: 'billing-web', provider: 'invoice-service', dir: 'pacts' });
const headers = { Accept: 'application/json', Authorization: regex('^Bearer .+$', 'Bearer test-token') };

describe('billing-web -> invoice-service', () => {
  it('gets one invoice', () => {
    pact
      .given('invoice inv_42 exists')
      .uponReceiving('a request for invoice inv_42')
      .withRequest({ method: 'GET', path: '/api/invoices/inv_42', headers })
      .willRespondWith({
        status: 200,
        headers: { 'Content-Type': regex('^application/json', 'application/json; charset=utf-8') },
        body: {
          id: string('inv_42'),
          customerId: uuid('8f3a2b1c-0000-4000-8000-000000000000'),
          currency: regex('^[A-Z]{3}$', 'USD'),
          total: decimal(129.99),
          issuedAt: regex('^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z$', '2026-01-15T09:30:00Z'),
          lines: eachLike({ sku: like('sku_pro'), quantity: integer(1) }),
        },
      });

    return pact.executeTest(async (mockServer) => {
      const invoice = await fetchInvoice(mockServer.url, 'inv_42', 'test-token');
      expect(invoice.id).toBe('inv_42');
      expect(invoice.lines.length).toBeGreaterThan(0);
    });
  });

  it('gets the shared 404 envelope for a missing invoice', () => {
    pact
      .given('invoice inv_missing does not exist')
      .uponReceiving('a request for a missing invoice')
      .withRequest({ method: 'GET', path: '/api/invoices/inv_missing', headers })
      .willRespondWith({
        status: 404,
        body: { error: { code: 'INVOICE_NOT_FOUND', message: like('Invoice not found.') } },
      });

    return pact.executeTest(async (mockServer) => {
      await expect(fetchInvoice(mockServer.url, 'inv_missing', 'test-token')).rejects.toMatchObject({ status: 404 });
    });
  });
});
```

```typescript
import { Verifier } from '@pact-foundation/pact';
import { it } from 'vitest';
import { seedInvoice, deleteInvoice } from './fixtures/invoices';

it('honours published consumer contracts', async () => {
  await new Verifier({
    provider: 'invoice-service',
    providerBaseUrl: 'http://127.0.0.1:8081', // the test instance this suite started
    pactBrokerUrl: process.env.PACT_BROKER_BASE_URL,
    pactBrokerToken: process.env.PACT_BROKER_TOKEN, // from the CI secret store
    providerVersion: process.env.GIT_SHA,
    providerVersionBranch: process.env.GIT_BRANCH,
    publishVerificationResult: process.env.CI === 'true',
    consumerVersionSelectors: [{ mainBranch: true }, { deployedOrReleased: true }, { matchingBranch: true }],
    enablePending: true,
    stateHandlers: {
      'invoice inv_42 exists': () => seedInvoice({ id: 'inv_42', total: 129.99 }),
      'invoice inv_missing does not exist': () => deleteInvoice('inv_missing'),
    },
    requestFilter: (req, _res, next) => {
      req.headers.authorization = 'Bearer test-token'; // accepted by the test instance only
      next();
    },
  }).verifyProvider();
}, 120_000);
```

Broker steps for CI (illustrative; `pact-broker` is the Pact Broker CLI, and
`record-deployment` needs the environment to exist in the broker):

```bash
pact-broker publish pacts --consumer-app-version "$GIT_SHA" --branch "$GIT_BRANCH" \
  --broker-base-url "$PACT_BROKER_BASE_URL" --broker-token "$PACT_BROKER_TOKEN"

pact-broker can-i-deploy --pacticipant invoice-service --version "$GIT_SHA" \
  --to-environment production --retry-while-unknown 6 --retry-interval 30

# Only after the deployment has succeeded:
pact-broker record-deployment --pacticipant invoice-service --version "$GIT_SHA" \
  --environment production
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Provider verification runs against local or ephemeral test instances only,
  never production URLs or production data.
- Ask before outward-facing broker actions from a local machine: publishing to
  a shared broker, recording deployments or releases, or changing webhooks.
  These normally belong in CI.
- Never loosen a matcher, delete an interaction, or disable verification to make
  a build pass. A failed verification is a real incompatibility; use pending
  pacts for expectations the provider has not built yet.
- Contracts verify interface shape. Keep pricing rules, workflow outcomes, and
  other business logic in unit and integration tests.
- Examples use synthetic data. Broker tokens come from CI secrets and are never
  committed or printed.

## Verification

Use the project's own commands (the script names below are illustrative). Run
each check separately and report its real result; never chain alternatives
with `||`.

- Consumer contract tests pass and write pact files.
- Determinism: the second run produces identical pact files.

  ```bash
  npm run test:contract
  snapshot="$(mktemp -d)"
  cp -R pacts "$snapshot/"
  npm run test:contract
  diff -r "$snapshot/pacts" pacts
  ```

  No `diff` output means the files are stable. The snapshot lives in a temporary
  directory outside the repository.
- Provider verification passes against the local test instance, with every
  provider state handled (an unhandled state is a failure, not a skip).
- The test code passes the project's type check and lint.

## Report

- **Boundary:** consumer, provider, transport, and pact-js version.
- **Interactions:** each one, its provider state, and its matcher strategy.
- **Coverage gaps:** consumer-invoked endpoints with no verified interaction.
- **Drift found:** failing interactions with the exact mismatch.
- **CI and broker:** what was wired (publish, verify, can-i-deploy, record-deployment).
- **Not verified:** checks that could not run and why.

## Optional delegation

- The `api-designer` subagent can review the underlying API contract while you
  write the tests.
- The `ci-verifier` subagent can confirm the new CI jobs run and report correctly.
- The `test-writer` subagent can add consumer interactions once the boundary
  inventory is agreed.
