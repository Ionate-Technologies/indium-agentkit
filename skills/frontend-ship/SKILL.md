---
name: frontend-ship
description: "Build or change a user-facing frontend feature (page, component, form, or client data flow) in the project's existing framework and design system, with the states it needs, WCAG 2.2 AA accessibility, and tests. Use when implementing UI from an agreed brief or API contract in Next.js, Remix or React Router, Vite, Vue or Nuxt, SvelteKit, or Angular apps. Not for UI review (delegate to the frontend-reviewer subagent) or accessibility audits (use the accessibility-audit skill)."
---

# Frontend Ship

Ship a UI feature that looks and behaves like the rest of the app, handles its
real states, and passes the project's checks. The stance is **the project's
stack and design system first**: reuse what exists, follow existing directory
conventions, and ask before inventing a look.

## When to use

- A page, component, form, or client-side data flow must be built or changed,
  and its behavior and API contract are known or can be settled with the user.
- An existing screen needs missing loading, empty, error, or unauthorized states.

## When not to use

- Reviewing finished UI work: delegate to the `frontend-reviewer` subagent.
- A WCAG audit of existing pages: use the `accessibility-audit` skill.
- The API does not exist yet: use the `api-design` skill, then the `backend-api` skill.
- A large or ambiguous feature that needs scoping first: use the `plan-change` skill.
- A measured performance regression: use the `performance-optimization` skill.
- Native or cross-platform mobile apps: use the `mobile-feature` skill.
- Translations, plurals, and locale formatting: use the `internationalize-ui`
  skill.
- End-to-end journey tests: use the `e2e-test-suite` skill.
- CORS, CSP, and security headers: use the `browser-security-config` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Behavior:** user goal, acceptance criteria, and which states apply (brief,
  ticket, or a feature-brief handoff).
- **Contract:** endpoints, response shapes, auth, and error codes, or the props
  the component receives.
- **Stack:** framework, router, and version from `package.json` and config files
  (see the table below).
- **Design system:** component library (for example `components/ui/`, shadcn/ui,
  MUI, Vuetify, Angular Material), token source (CSS custom properties, Tailwind
  config or `@theme`, theme files), Storybook stories, icons, and fonts.
- **Data and state conventions:** the existing API client, data library
  (TanStack Query, SWR, Apollo), stores, form library, and validation schemas.
- **Tests and budgets:** component and end-to-end harnesses, and any bundle or
  Lighthouse budget (size-limit, bundlesize, Lighthouse CI). Commands come from
  `AGENTS.md`, `CLAUDE.md`, package scripts, or the `Makefile`.

| Signal | Stack | Where data and secrets belong |
| --- | --- | --- |
| `next`, routes under `app/` or `src/app/` | Next.js App Router | Server Components, route handlers, server actions; `'use client'` only at interactive leaves |
| `next`, routes under `pages/` or `src/pages/` | Next.js Pages Router | `getServerSideProps` or `getStaticProps`, API routes |
| `@remix-run/*`, or `@react-router/dev` with `react-router.config.ts` | Remix or React Router framework mode | Route `loader` and `action` functions |
| `vite.config.*` with no server framework | Vite single-page app | The app's authenticated API client; secrets stay on the backend |
| `nuxt`, `nuxt.config.*` | Nuxt | `useFetch` or `useAsyncData`, `server/api` routes; private `runtimeConfig` keys |
| `@sveltejs/kit`, `svelte.config.js` | SvelteKit | `+page.server.ts` load and form actions; `$env/static/private` |
| `@angular/core`, `angular.json` | Angular | `HttpClient` services and interceptors; follow standalone or NgModule style as the project does |

A Next.js app can use both routers; follow the one the target route lives in.

## Workflow

1. **Orient.** Read `AGENTS.md`, `package.json`, the framework config, and two
   sibling features similar to the target. Note where routes, components, hooks,
   styles, and tests live, and place new files beside their siblings. Do not
   create new top-level directories or scaffold guessed paths.
2. **Settle the design source.**
   - With a design system: reuse its components and tokens. Add a token only when
     no fitting one exists, in the token source, and call it out in the report.
   - Without one: ask the user before choosing an aesthetic. Offer one or two
     options derived from the app's current styles; never default to a novelty
     look. Glassmorphic or 3D effects are only for an explicit request with no
     design system to follow; use the corrected recipes in
     `references/visual-styles.md` in this skill's directory, which keep AA
     contrast, reduced-motion, and fallback rules.
3. **Place the data and auth boundary.**
   - Fetch on the server where the framework allows it (row in the table above),
     and pass only serializable, non-secret data to client components.
   - In the browser, call the app's own endpoints through its authenticated
     client (session cookies or the existing interceptor).
   - Never pass API keys or bearer tokens as props, URL parameters, or public
     environment variables (`NEXT_PUBLIC_`, `VITE_`, `NUXT_PUBLIC_`, SvelteKit
     `PUBLIC_`). Enforce authorization on the server; hiding a button is not
     access control.
4. **Choose the states that apply,** and skip the rest with a reason:
   - **Loading:** skeleton or placeholder sized like the final content so the
     layout does not shift.
   - **Empty:** says what is missing and offers the next action.
   - **Error with recovery:** plain-language message without raw server text or
     stack traces, a retry for transient failures, and preserved form input.
   - **Success:** the data, or a confirmation for a mutation.
   - **Unauthorized (401):** route to sign-in through the app's auth flow.
     **Forbidden (403):** explain the missing access and how to request it.
   - **Retries:** automatic only for idempotent reads that failed transiently
     (network error, 5xx, or 429, honoring `Retry-After` when sent), with capped
     exponential backoff, jitter, a small attempt limit, and cancellation on
     unmount. Never auto-retry a mutation unless the API supports idempotency
     keys. If the data library already retries (TanStack Query does by default),
     configure it instead of adding a second loop.
5. **Implement.**
   - Type props and responses; validate untrusted input with the project's
     schema library where it has one.
   - Effects depend on stable primitive values, never on array or object
     identity created during render. Abort in-flight requests, clear timers, and
     unsubscribe in cleanup.
   - Semantic HTML first, ARIA only where native elements fall short. Every
     control has an accessible name; forms have labels, `autocomplete` values,
     and errors linked with `aria-describedby`.
   - Keyboard: all operable, logical order, visible focus that sticky headers do
     not cover; Escape closes overlays and focus returns to the trigger.
   - Announce async changes through one always-mounted `role="status"` region;
     use `role="alert"` for errors, never nested inside another live region.
   - Contrast at least 4.5:1 for text and 3:1 for large text, icons, and control
     boundaries; targets at least 24 by 24 CSS px; no color-only meaning; honor
     `prefers-reduced-motion`; allow paste and password managers at sign-in.
   - No `dangerouslySetInnerHTML`, `v-html`, `{@html}`, or `[innerHTML]` with
     unsanitized input. No mock data in production paths; fixtures live in tests
     and stories.
6. **Test at public seams.** Component tests cover each implemented state and
   the main interaction, querying by role and label. Add an end-to-end test for
   the main path when the project has a harness. Mock the network at the
   boundary (MSW, `page.route`), not the component under test. Run the project's
   axe check if it has one.
7. **Check performance.** Core Web Vitals "good" thresholds are LCP at most
   2.5 s, INP at most 200 ms, and CLS at most 0.1, measured at the 75th
   percentile of real page loads. Lab tools approximate them: Lighthouse reports
   LCP and CLS, and INP needs real or scripted interactions. Give images
   dimensions, do not lazy-load the LCP image, reserve space for async content,
   code-split heavy client-only widgets, and keep event handlers short. Compare
   bundle output before and after against the project's budget; without a
   budget, report the delta rather than inventing one.
8. **Inspect the diff** for scope creep, `console.log`, secrets, hard-coded
   colors or spacing that bypass tokens, and generated files, then report.

## Reference: client-side read with states (React)

Illustrative. Use it when data must load in the browser (a single-page app or
a client-only interaction); in server-rendering frameworks, fetch on the server
first. Swap in the project's API client, data library, and design-system
components.

```tsx
'use client'; // Only needed in React Server Component frameworks.

import { useEffect, useId, useState } from 'react';

type Order = { id: string; label: string };

type View =
  | { status: 'loading' }
  | { status: 'success'; orders: Order[] }
  | { status: 'empty' }
  | { status: 'unauthorized' }
  | { status: 'forbidden' }
  | { status: 'error' };

class HttpError extends Error {
  status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

const MAX_AUTO_RETRIES = 2;

const STATUS_TEXT: Record<View['status'], string> = {
  loading: 'Loading orders…',
  success: '',
  empty: 'No orders yet.',
  unauthorized: 'Sign in to see your orders.',
  forbidden: 'You do not have access to these orders.',
  error: '',
};

// Render as <OrderList key={customerId} customerId={customerId} /> so a
// different customer starts again from the loading state.
export function OrderList({ customerId }: { customerId: string }) {
  const headingId = useId();
  const [view, setView] = useState<View>({ status: 'loading' });
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    // Drop results that arrive after this effect was cleaned up.
    const commit = (next: View) => {
      if (!controller.signal.aborted) setView(next);
    };

    async function load(attempt: number): Promise<void> {
      try {
        // Same-origin request: the session cookie authenticates it.
        const response = await fetch(
          `/api/customers/${encodeURIComponent(customerId)}/orders`,
          { signal: controller.signal, headers: { Accept: 'application/json' } },
        );
        if (response.status === 401) return commit({ status: 'unauthorized' });
        if (response.status === 403) return commit({ status: 'forbidden' });
        if (!response.ok) throw new HttpError(response.status);
        const data: unknown = await response.json();
        // Replace with the project's schema validation if it has one.
        if (!Array.isArray(data)) throw new Error('Unexpected response shape');
        const orders = data as Order[];
        commit(orders.length > 0 ? { status: 'success', orders } : { status: 'empty' });
      } catch (error) {
        if (controller.signal.aborted) return;
        // Retry this idempotent read only for network errors (fetch rejects
        // with TypeError) and 5xx responses. A fuller version would also
        // honor Retry-After on 429 and 503.
        const transient =
          error instanceof HttpError ? error.status >= 500 : error instanceof TypeError;
        if (transient && attempt < MAX_AUTO_RETRIES) {
          const delayMs = 500 * 2 ** attempt + Math.random() * 250;
          retryTimer = setTimeout(() => void load(attempt + 1), delayMs);
          return;
        }
        commit({ status: 'error' });
      }
    }

    void load(0);
    return () => {
      controller.abort();
      clearTimeout(retryTimer);
    };
  }, [customerId, reloadCount]);

  function retry() {
    setView({ status: 'loading' });
    setReloadCount((count) => count + 1);
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Orders</h2>
      {/* One polite live region, always mounted so updates are announced. */}
      <p role="status">{STATUS_TEXT[view.status]}</p>
      {view.status === 'error' && (
        <>
          <p role="alert">Orders could not be loaded.</p>
          <button type="button" onClick={retry}>Try again</button>
        </>
      )}
      {view.status === 'unauthorized' && <a href="/login">Sign in</a>}
      {view.status === 'success' && (
        <ul>
          {view.orders.map((order) => (
            <li key={order.id}>{order.label}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

A matching Playwright test mocks the network with
`page.route('**/api/customers/*/orders', ...)` and asserts through
`page.getByRole('region', { name: 'Orders' }).getByRole('status')`.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including deploys and preview publishes.
- Never weaken a test, lint rule, type check, or budget to make work pass.
- Ask before adding or upgrading dependencies, including UI kits, icon sets,
  and fonts.
- Do not change shared tokens, root layouts, global config, or routing config
  unless the task needs it; name each such change in the report.
- Never put secrets or bearer tokens in client code, client props, public
  environment variables, URLs, or browser storage the app does not already use
  for auth.
- Never remove a focus indicator without a visible replacement.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Type check (for example the project's `typecheck` script, `vue-tsc`,
  `svelte-check`, or the Angular build): no new errors.
- Lint, including any accessibility lint plugin: clean for changed files.
- Component tests for each implemented state, and the focused end-to-end test,
  pass.
- Production build succeeds; bundle delta is within the project's budget or
  reported.
- Manual pass in a browser when one is available: keyboard through the feature,
  200% zoom, a narrow viewport, and reduced motion.

## Report

- **Stack and conventions:** framework, router, design system, and the sibling
  code you followed.
- **Changed files:** path and purpose; any shared token, layout, or config change.
- **States:** implemented, and skipped with the reason.
- **Data and auth boundary:** where data is fetched and how requests authenticate.
- **Accessibility:** checks run and results.
- **Performance:** bundle delta and any Web Vitals measurement, with the tool.
- **Verification:** each command and its result.
- **Not verified:** browsers, devices, screen readers, or field metrics not exercised.

## Optional delegation

The `frontend-builder` subagent can implement a bounded slice when you give it
the behavior, contract, assigned paths, and verification commands. Afterwards,
the `frontend-reviewer` subagent can review the diff and the
`accessibility-checker` subagent can audit the result in parallel. Re-run any
check a subagent reports before relying on it.
