---
name: e2e-test-suite
description: "Set up or extend end-to-end tests for a small set of business-critical user journeys with the project's tool (Playwright by default for web, Cypress if present, Detox or Maestro for mobile), using isolated seeded data, saved sign-in state, role-based locators, web-first assertions, boundary mocks, and traces on failure. Use when adding or fixing an e2e suite or covering sign-in, checkout, or core create and edit flows. Not for component or unit tests (use the test-first-change skill) or flaky tests (use the flaky-test-triage skill)."
---

# End-to-End Test Suite

Cover the few journeys that would hurt the business most if they broke, with
tests that are independent, fast, and trustworthy enough to gate merges. The
stance is **few journeys, real stack, no sleeps**: every test owns its data,
waits on observable state, and runs against a local or ephemeral environment,
never production.

## When to use

- A project has no end-to-end suite, or its suite is slow, brittle, or ignored.
- A business-critical journey (sign-in, sign-up, checkout, a core create or
  edit flow) needs coverage before release.
- Moving an existing suite to stable locators, saved sign-in state, parallel
  runs, or CI artifacts.

## When not to use

- Component, unit, or API tests for a feature: use the `test-first-change`
  skill, or the `frontend-ship` skill while building the UI.
- A test that passes and fails on the same code: use the `flaky-test-triage`
  skill.
- Checks between services or behavior under traffic: use the
  `contract-testing` or `load-testing-suite` skill.
- An accessibility audit: use the `accessibility-audit` skill (its axe scans
  can run inside this suite).

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- The existing tool and config (`playwright.config.*`, `cypress.config.*`,
  `.detoxrc.*`, a `.maestro/` folder) and the test and CI commands in
  `AGENTS.md`, package scripts, or the `Makefile`. Extend what exists; do not
  add a second framework.
- The journeys that matter, from product owners, analytics, incident history,
  and the routes that handle money or sign-in.
- How the app runs and is seeded for tests (local server, Docker Compose, or
  ephemeral preview environments), and how users sign in (password, SSO, MFA).
- Test accounts and test-mode credentials available as CI secrets, and each
  third party the journeys touch, called from the browser or the backend.
- The time budget for a merge-blocking check. Use the project's policy; for
  example, under 10 minutes.

## Workflow

1. **Pick the journeys.** List candidates with what breaks if each fails, then
   choose a small set (for example 5 to 15) that are business-critical and
   cross several layers. Test the main path and one or two critical failures
   (wrong password, declined payment) end to end; push edge cases and
   validation permutations down to component or API tests. Record the list in
   the suite's README or test plan so additions are deliberate.
2. **Fix the target environment.** Run against a local server (Playwright
   `webServer`) or an ephemeral environment seeded for the run. Read the base
   URL from configuration and make the config refuse production hostnames (see
   the example). Ask before running against a shared staging environment; never
   run against production.
3. **Give every test its own data.** Create what a test needs through the
   app's API or a seed step, with unique names (worker index plus a time or
   random suffix), and assert only on data the test created. Never depend on
   test order or on data another test changes. Use the
   `synthetic-data-generation` skill for seed scripts, and never copy real
   customer data into fixtures. On an environment that outlives the run,
   delete created data in teardown.
4. **Sign in once and reuse the state.** Sign in through the UI in a setup
   step, save the browser storage state, and load it in every test (Playwright
   setup project plus `storageState`; Cypress `cy.session()`). Keep one
   dedicated sign-in journey that exercises the real form, including a failure.
   - Share one account across parallel workers only if tests never change
     account-level state (settings, plan, cart) and touch only data they
     create. Otherwise give each worker its own account, for example through a
     worker-scoped fixture keyed by `test.info().parallelIndex`.
   - Signed-out tests override the state, for example
     `test.use({ storageState: { cookies: [], origins: [] } })`.
   - Storage state files hold live session cookies: add their folder (for
     example `playwright/.auth/`) to `.gitignore`. Read credentials from CI
     secrets. For MFA, use test accounts whose TOTP secret is a CI secret, or
     the identity provider's test mode; never disable MFA in shared config.
5. **Locate elements the way users find them.** Prefer, in order,
   `getByRole(role, { name })`, `getByLabel`, `getByText` or
   `getByPlaceholder`, then `getByTestId` (attribute `data-testid` by default,
   configurable with `testIdAttribute`) for elements without an accessible
   name. Avoid CSS chains, XPath, and `nth()` positions; scope within a
   container (a row, a dialog) instead. A control with no accessible name is an
   accessibility bug too, so fix it in the app. Playwright locators are strict:
   an action on a locator that matches several elements fails instead of
   guessing. In Cypress, use `@testing-library/cypress` queries such as
   `cy.findByRole` if present, else `data-cy` or `data-testid`. On mobile, use
   React Native `testID` (Detox `by.id`), accessibility labels, or Maestro `id`.
6. **Wait on state, never on time.** Use web-first assertions that retry until
   they pass or time out: `await expect(locator).toBeVisible()`,
   `toHaveText`, `toHaveURL`. Never add `page.waitForTimeout`, `cy.wait(5000)`,
   or `sleep`, and do not wait for `networkidle`, which Playwright discourages.
   Use `page.waitForResponse` only when the UI shows no signal, and
   `expect.poll` for backend state that settles eventually. Detox and Maestro
   wait for the app to go idle; in Detox, add `waitFor(...).withTimeout(...)`
   only for a specific element.
7. **Mock only at the boundary.** Keep the app's own frontend and backend real;
   that is what an end-to-end test proves.
   - Stub third parties the browser calls (maps, chat widgets, analytics) with
     `page.route()` or `cy.intercept()`.
   - Third parties the backend calls (payments, email, SMS) are invisible to
     browser routing. Point the backend at the provider's sandbox or test mode,
     or a local stub server, through environment configuration.
   - Never send real messages or charges. Force a rare error state (a 500 from
     your own API) with a route mock only in a few dedicated tests.
8. **Run tests in parallel.** Every test must pass alone and in any order, so
   enable full parallelism (`fullyParallel: true`) and avoid serial mode. When
   one machine is too slow, shard across CI jobs
   (`npx playwright test --shard=1/4`) with the blob reporter, then combine with
   `npx playwright merge-reports`. Cypress parallelizes through Cypress Cloud
   (`--record --parallel`) or a spec-splitting step; use what the project has.
9. **Retry as a mitigation, never as the fix.** Allow a small retry count in CI
   only (for example 1 or 2, per project policy) and none locally, and set
   `forbidOnly` in CI so a stray `test.only` fails the run. Playwright reports a
   test that passed on retry as flaky: record each one in a tracked issue and
   use the `flaky-test-triage` skill. Never raise global timeouts to hide a
   flake. Before merging a new test, repeat it, for example
   `npx playwright test e2e/projects.spec.ts --repeat-each=20`.
10. **Keep evidence on failure.** Record a trace (`trace: 'on-first-retry'` or
    `'retain-on-failure'`), screenshots, and video on failure, and upload the
    HTML report and results folder as CI artifacts; open a trace with
    `npx playwright show-trace`. Traces capture network traffic and cookies, so
    use test accounts only and keep retention short. For Detox and Maestro
    artifact options, check `detox test --help` or `maestro test --help`.
11. **Gate merges within the budget.** Wire the suite into CI with the
    `ci-pipeline` skill (browsers install with
    `npx playwright install --with-deps`). If the full suite exceeds the budget,
    split it: a tagged smoke set (for example `@smoke`, selected with
    `--grep @smoke`) blocks merges, and the full set runs on main or nightly.
12. **Mobile journeys.** Run Detox or Maestro on simulators or emulators from a
    test build. Start from a known state: Maestro `launchApp` with
    `clearState: true`, or Detox `device.launchApp({ delete: true })`, which
    reinstalls and is slow, so prefer fresh per-test data. Sign in through the
    real UI or pass a session through a test build's launch arguments; no
    test-only path may exist in release builds. Ask before paid device-farm
    runs. Use the `mobile-feature` skill for the feature code itself.

## Worked example: Playwright with saved sign-in (illustrative TypeScript)

A setup project signs in once and saves the storage state; the browser project
depends on it and loads that state for every test. Add a `webServer` block if
the suite should start the app.

```ts
// playwright.config.ts (excerpt)
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
if (new URL(baseURL).hostname === 'app.example.com') {
  throw new Error('Refusing to run end-to-end tests against production');
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' },
      dependencies: ['setup'],
    },
  ],
});
```

```ts
// e2e/auth.setup.ts
import { test as setup, expect } from '@playwright/test';

setup('sign in', async ({ page }) => {
  const email = process.env.E2E_USER_EMAIL;
  const password = process.env.E2E_USER_PASSWORD;
  if (!email || !password) throw new Error('Set E2E_USER_EMAIL and E2E_USER_PASSWORD');

  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await page.context().storageState({ path: 'playwright/.auth/user.json' });
});
```

```ts
// e2e/projects.spec.ts
import { test, expect } from '@playwright/test';

test('signed-in user can rename a project', async ({ page }) => {
  // A browser-side third party, stubbed at the boundary. The app's API stays real.
  await page.route('https://widgets.chat-vendor.example/**', (route) => route.fulfill({ status: 204 }));

  // The test owns its data: created through the app's API with a unique name.
  // page.request shares the signed-in cookies and the configured baseURL.
  const name = `E2E project ${test.info().parallelIndex}-${Date.now()}`;
  const created = await page.request.post('/api/projects', { data: { name } });
  await expect(created).toBeOK();
  const { id } = await created.json();

  await page.goto(`/projects/${id}/settings`);
  await page.getByLabel('Project name').fill(`${name} renamed`);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status')).toHaveText('Changes saved');

  await page.goto('/projects');
  await expect(page.getByRole('link', { name: `${name} renamed` })).toBeVisible();
});
```

This test changes only a project it created, so one shared account is safe. A
test that changes account settings needs a per-worker account. If the API
requires a CSRF token, seed through a seed script instead of `page.request`.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including runs against shared staging, device-farm runs, changes to required
  CI checks, and new test dependencies (use the `evaluate-new-dependency`
  skill).
- Never weaken a test, check, or threshold to make work pass: no added sleeps,
  raised global timeouts, extra retries, or `skip` and `fixme` without a
  tracked issue and an owner.
- Never run against production or with production credentials, and never send
  real messages or payments; use sandboxes, test modes, or stubs.
- Never commit storage state files, test credentials, or traces, and treat CI
  artifacts as sensitive. Test-only hooks (seed endpoints, sign-in shortcuts)
  must be disabled outside test environments; confirm a production build does
  not expose them.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Each new test passes alone, in the full parallel run, and when repeated (for
  example `--repeat-each=20`) without using a retry.
- Each new test fails for the right reason: temporarily break the expectation
  or the feature, confirm a clear failure message and a trace, then revert
  your own temporary change.
- The diff has no `waitForTimeout`, numeric `cy.wait`, `sleep`, `.only`, or new
  CSS or XPath locators.
- In CI, the suite passes, artifacts upload on a forced failure, and the
  merge-blocking job stays within the time budget.
- `git status` shows no storage state, credentials, or trace files to commit.

## Report

- **Journeys:** covered, and deliberately not covered with the reason.
- **Environment and data:** where tests run, the production guard, seeding,
  and the account strategy per worker.
- **Mocks:** each stubbed third party and how (route, sandbox, stub server).
- **Stability:** repeat-run results, retries configured, flaky tests tracked.
- **CI:** run time, sharding, smoke and full split, and artifacts kept.
- **Not verified:** checks that could not run and why (for example no CI
  secrets for test accounts).

## Optional delegation

The `test-writer` subagent can write individual journey tests once the
patterns, fixtures, and file paths are agreed. The `synthetic-data-architect`
subagent can design per-worker seed data. The `frontend-builder` or
`mobile-builder` subagent can add missing accessible names or test IDs in app
code. The `ci-verifier` subagent can diagnose a failing CI run. The workflow
above stays complete for a single agent.
