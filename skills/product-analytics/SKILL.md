---
name: product-analytics
description: "Add or change product analytics events and A/B experiments from a reviewed tracking plan: typed, versioned event schemas, consistent names, no personal data or free text sent to vendors, consent and region checks, client and server deduplication, safe renames, and experiments with stable assignment, exposure logged when the variant is shown, sample ratio checks, and metrics fixed before launch. Use when adding tracking, instrumenting a funnel, or setting up an A/B test. Not for operational telemetry (use the observability-setup skill)."
---

# Product Analytics

Instrument product behavior so the data answers a decided question, survives
renames, and never carries personal data to a vendor. The stance is **plan
before code, and decide the analysis before the data arrives**: every event has
a reviewed tracking-plan entry, and every experiment has its metrics, sample
size, and stopping rule written down before launch.

## When to use

- Adding, changing, renaming, or removing analytics events or properties.
- Instrumenting a funnel, onboarding flow, or feature for adoption metrics.
- Setting up, launching, or debugging an A/B or multivariate experiment.
- An existing tracking setup sends personal data, double counts, or broke a
  dashboard.

## When not to use

- Logs, metrics, traces, and alerts for operators: use the
  `observability-setup` skill.
- Rolling out, gating, or removing a feature flag that is not an experiment:
  use the `feature-flag-lifecycle` skill.
- Answering a business question or analyzing experiment results from the
  warehouse: use the `analyze-data` skill.
- Assessing GDPR or other regulatory readiness of the analytics data flow: use
  the `compliance-audit` skill.
- Warehouse models and pipelines built on the events: use the
  `data-pipeline-design` skill.
- Deleting analytics data for an erasure request: use the
  `data-retention-and-erasure` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The analytics SDK and destinations (for example Segment, RudderStack,
  Amplitude, Mixpanel, PostHog, GA4, Snowplow, or an in-house collector), and
  where it is initialized.
- The existing tracking plan or event registry (a YAML or JSON file, a schema
  registry, or a vendor tool) and its naming conventions.
- The question each new event or experiment must answer, and who owns it.
- The consent mechanism (a consent management platform or an in-house banner),
  its categories, and the privacy owner's rules on identifiers, hashing, and
  regions.
- The experiment platform, if any (for example GrowthBook, Statsig, Optimizely,
  LaunchDarkly, Eppo, or in-house), and whether its SDK logs exposure itself.
- Dashboards, warehouse models, saved queries, and experiment metrics that read
  existing events.
- A non-production project, write key, or debug mode for QA.

## Workflow

1. **Start from the decision.** Write the question and the decision it informs
   (for example "does the new checkout copy raise completed checkouts?"). Track
   only what answers a question; "track everything" fills the warehouse with
   unowned events and personal data.
2. **Write the tracking-plan entry before code**, and get it reviewed by the
   event owner and, for anything near personal data, the privacy owner. Per
   event: name, trigger (the exact user action or system event and where it
   fires), source (client or server), properties with types, units, allowed
   values, and required or optional, owner, purpose, destinations, consent
   category, schema version, and status (proposed, active, deprecated). Keep the
   plan in the repository next to the code.
3. **Name consistently.** Follow the existing convention. If there is none, use
   `object_action` in snake_case with a past-tense verb (`checkout_completed`,
   `invite_sent`). Never put values in names (`button_blue_clicked`); make them
   properties. Use one unit per property (money as integer minor units plus an
   ISO 4217 `currency`, timestamps as ISO 8601 UTC) and closed enums.
4. **Keep personal data out.** Never send names, email addresses, phone numbers,
   postal addresses, precise location, payment data, credentials, tokens, or
   free-text input (search terms, form fields, messages) to an analytics vendor.
   - Identify users with an internal pseudonymous ID or the SDK's anonymous ID.
     Hash an identifier only if the privacy policy says to; a hash of an email
     is still personal data and can be reversed by guessing likely inputs.
   - Strip query strings and fragments from captured URLs and referrers, or
     allowlist parameters; reset and invite links often carry tokens or emails.
   - Turn off or mask autocapture and session replay for inputs and text by
     default, if the SDK has them.
   - Enforce this in one wrapper that drops properties not in the schema.
5. **Check consent and region before tracking.** Do not initialize the SDK, set
   identifiers, or send events until the user's consent state allows that
   category, where policy requires prior consent (for example for non-essential
   device identifiers in the EU and UK). Decide with the privacy owner whether
   pre-consent events are dropped or held, honor withdrawal (stop sending and
   reset the identifier), and honor opt-out signals the policy names, such as
   Global Privacy Control. This skill implements the policy; it does not decide
   the legal basis.
6. **Implement through one typed module.** Define events as types (generated
   from the plan where tooling allows) and call a single `track` function that
   validates the payload, applies the consent gate, adds common context (event
   ID, schema version, timestamp, app version, platform), and sends. Do not
   scatter direct vendor SDK calls.
7. **Choose the source and deduplicate.**
   - Fire business-critical events (order placed, subscription started) on the
     server from the system of record, after the transaction commits; use an
     outbox or job queue as the `background-jobs-and-queues` skill describes.
   - Client events (views, clicks) lose data to ad blockers, browser tracking
     prevention, closed tabs, and flaky networks. Do not use them for revenue or
     counts that must reconcile. A first-party proxy reduces blocklist loss but
     never overrides a user's opt-out or missing consent.
   - Give every event an `event_id` generated once and reused on retries; when
     client and server can both report the same fact, derive the ID from the
     business key or pass it from client to server so the pipeline keeps one.
     Map it to the vendor's deduplication field (for example Amplitude
     `insert_id` or Mixpanel `$insert_id`) and check that vendor's window.
   - For events fired while the page unloads, use the SDK's beacon or
     keepalive transport.
8. **Change events without silently breaking consumers.** A rename, a changed
   meaning, or a changed property type breaks dashboards, funnels, cohorts, and
   experiment metrics without an error. Find every consumer first and tell the
   owners. Then add the new event or schema version alongside the old one,
   dual-send, migrate consumers, confirm the counts match, mark the old event
   deprecated with a removal date, and remove it last. Never reuse a name for a
   new meaning. A vendor display-name change does not update raw exports or
   warehouse tables.
9. **Design experiments before building them.** Write a plan with: hypothesis;
   randomization unit (user, account, device, or session; use the unit the
   change affects, for example the account when users share a workspace); one
   primary metric; secondary and guardrail metrics (errors, latency, revenue,
   unsubscribes, support contacts); the minimum detectable effect, significance
   level, and power; the sample size and a duration in whole weeks; the analysis
   method (fixed horizon or sequential); and exclusions. Have the owner approve
   it, then freeze it.
10. **Assign stably.** Hash the experiment key (or a per-experiment salt) with
    the unit ID into buckets, so a unit keeps its variant across sessions and
    restarts, and experiments do not correlate. Logged-out device IDs change
    across devices; say so in the plan. Changing the split during the test mixes
    populations; analyze phases separately or restart. Run experiments that
    touch the same surface in mutually exclusive groups.
11. **Log exposure when the user actually sees the variant**, at the same point
    in every arm including control, not at assignment, login, or app start.
    Exposure at assignment counts users who never saw the change and dilutes
    the effect. Many experiment SDKs log exposure automatically when code reads
    the variant; then read it only where the variant renders, never in a
    prefetch or a global initializer. Deduplicate exposures per unit and
    experiment.
12. **Check sample ratio mismatch** on exposed counts daily and before any
    analysis. chi-squared = sum over arms of (observed - expected) squared,
    divided by expected. With two arms, a value above 10.83 means p below
    0.001, a common threshold (use the project's). A mismatch means assignment
    or logging is broken: stop, find the cause (bot filtering, redirects,
    crashes, caching, exposure logged in one arm only), and do not analyze.
13. **Analyze as planned.** With a fixed-horizon test, do not look at the
    primary metric repeatedly and stop when it turns significant; that inflates
    false positives. If early stopping is needed, use a sequential method the
    platform supports. Stopping early for harm on a guardrail is a safety call,
    not a win. Report confidence intervals, not only p-values. When a metric's
    denominator is not the randomization unit (for example clicks per session
    in a user-randomized test), use the delta method or a bootstrap. Treat segment results as
    exploratory. Use the `analyze-data` skill for the analysis itself.
14. **QA in a debug or test mode.** Send QA traffic to a non-production project
    or the vendor's debug view, never the production project. Confirm each
    event fires once per trigger with correct names, types, and IDs; nothing is
    sent before consent or after withdrawal; payloads in the network inspector
    contain no personal data; exposure fires on render in every arm; and the
    assignment is stable across reloads.
15. **Document.** Mark plan entries active with their version, record schema
    changes in the plan's changelog, and record each experiment's plan, result,
    and decision. Remove experiment code paths and their flag after the
    decision, using the `feature-flag-lifecycle` skill.

## Worked example: typed event and exposure log (illustrative TypeScript)

`consent`, `transport`, and `useExperimentVariant` stand for the project's own
modules.

```ts
type CheckoutCompleted = {
  name: "checkout_completed";
  version: 2;
  properties: {
    order_id: string;      // internal ID, never a payment reference
    amount_minor: number;  // integer minor units
    currency: string;      // ISO 4217, for example "EUR"
    item_count: number;
    payment_method: "card" | "wallet" | "bank_transfer";
  };
};

type ExperimentExposed = {
  name: "experiment_exposed";
  version: 1;
  properties: { experiment_key: string; variant: string };
};

export type AnalyticsEvent = CheckoutCompleted | ExperimentExposed;

export function track(event: AnalyticsEvent, eventId: string = crypto.randomUUID()): void {
  if (!consent.allows("analytics")) return; // one consent gate for every event
  transport.send({
    event_id: eventId,                      // reused on retries for deduplication
    name: event.name,
    schema_version: event.version,
    properties: event.properties,
    sent_at: new Date().toISOString(),
  });
}
```

```tsx
function CheckoutButton() {
  const variant = useExperimentVariant("checkout_copy"); // assignment only
  useEffect(() => {
    // Exposure when the variant renders, in every arm. React StrictMode runs
    // effects twice in development; deduplicate per unit and experiment
    // before sending (not shown).
    track({ name: "experiment_exposed", version: 1,
            properties: { experiment_key: "checkout_copy", variant } });
  }, [variant]);
  return <button>{variant === "treatment" ? "Pay now" : "Checkout"}</button>;
}
```

Sample size per arm for a conversion metric, approximately:
n = 2 x (z_alpha/2 + z_beta) squared x p(1 - p) / delta squared. With a 10%
baseline, a 1 point absolute effect, alpha 0.05 two-sided (z = 1.96), and 80%
power (z = 0.84), n is about 14,000 per arm. Use the platform's calculator and
the project's thresholds. For SRM, 10,000 versus 10,500 exposed users in a 50/50
test gives chi-squared of about 12.2: a mismatch, even though it looks small.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  launching or stopping an experiment, changing traffic splits, deleting or
  hiding events in a vendor, changing vendor project settings, or adding a new
  data destination.
- Never send personal data, secrets, or free-text input to an analytics vendor,
  and never send events the user's consent state does not allow.
- Never rename, retype, or remove an event in place while consumers read it.
- Never change an experiment's primary metric, sample size, or stopping rule
  after launch without recording the change and the reason.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Unit tests cover the wrapper: schema validation, dropped unknown properties,
  the consent gate, and stable event IDs on retry.
- A component or integration test shows exposure logs on render, once, in every
  arm, and not at assignment.
- A debug-mode session shows each planned event with the right properties and
  no personal data in the network payloads.
- With consent denied, the network inspector shows no analytics requests.
- Server-side events appear once when the client also reports them.
- Type check, lint, and the project's test suite pass.

## Report

- **Tracking plan:** events added, changed, or deprecated, with versions and
  owners, and where the plan lives.
- **Privacy:** identifiers used, properties dropped or hashed, consent and
  region handling, and the privacy owner's sign-off.
- **Sources and deduplication:** client or server per event, and the event ID
  strategy.
- **Experiment:** plan (unit, metrics, MDE, sample size, duration, method),
  exposure point, and SRM check result, if any.
- **Consumers:** dashboards and models migrated, and the deprecation timeline.
- **Verification:** each command and its result, and debug-mode evidence.
- **Not verified:** vendor-side processing, ad-blocker loss rates, and anything
  that needs production traffic.

## Optional delegation

The `compliance-auditor` subagent can review the analytics data flow for
personal data and consent handling. The `frontend-reviewer` subagent can check
exposure placement and render behavior. The `test-writer` subagent can write
the wrapper and exposure tests. The workflow above stays complete for a single
agent.
