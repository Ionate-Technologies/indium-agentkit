---
name: observability-setup
description: "Add or improve structured logging, metrics, OpenTelemetry tracing, and alerts in application code using the project's existing libraries, with central redaction, bounded label cardinality, and actionable SLO-based alerts that link a runbook. Use when a service cannot answer an operator question from its signals, new code needs instrumentation, or alerts are noisy, unowned, or missing. Not for writing the runbook itself (use the write-runbook skill) or tuning a slow path (use the performance-optimization skill)."
---

# Observability Setup

Instrument a service so operators can tell what is failing, for whom, and why,
from production signals alone. The stance is **answer operator questions with
the stack you already have**: every signal maps to a question, every page maps
to an action, and nothing sensitive leaves the process.

## When to use

- A service lacks the logs, metrics, or traces needed to diagnose a failure, or
  new endpoints, jobs, or integrations need instrumentation before release.
- Alerts are noisy, duplicated, unowned, cause-based, or missing a runbook link.
- Logs or telemetry may contain credentials or personal data.

## When not to use

- An incident is in progress: use the `incident-triage` skill.
- The task is the operator procedure behind an alert: use the `write-runbook`
  skill.
- A specific path is slow and needs profiling: use the
  `performance-optimization` skill.
- Collector, agent, or monitoring infrastructure configuration needs review: use
  the `infrastructure-review` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The operator questions to answer: which requests fail, how slow, for which
  route or tenant class, and which dependency is at fault.
- Existing libraries (logger, metrics client, tracing SDK, auto-instrumentation)
  from dependency manifests and instrumentation modules, and their destinations
  (OTLP endpoint, collector, `/metrics` scrape, log shipping, sampling).
- Conventions: log field names, levels, metric naming, and the semantic
  conventions version the existing instrumentation emits.
- SLOs, alert rule files, on-call routing, ownership, and where runbooks live.
- Data classification: which fields are personal data, credentials, or
  otherwise sensitive.

## Workflow

1. **Discover the stack.** Reuse the established libraries, formats, and
   destinations. Never add a competing framework or a new telemetry destination
   without approval. If nothing exists, propose OpenTelemetry as a vendor-neutral
   default and ask before adding dependencies.
2. **Gap analysis.** Map each operator question to a signal, and list what is
   missing. Do not instrument anything no question needs.
3. **Structured logs at decision points.** Request entry and outcome (unless
   access logs already cover it), authorization decisions, data mutations,
   external calls, errors, retries, and fallbacks. Use the project's field names
   and levels, and include the trace and span IDs so logs join traces (most
   OpenTelemetry SDKs offer a logging bridge for this). Avoid per-request debug
   logs on hot paths.
4. **Central redaction.** Redact in one auditable place, the logger's
   configuration or a processor or filter on every handler, not ad hoc at call
   sites. Cover at least passwords, tokens, secrets, API keys, `Authorization`
   and `Cookie` headers, session IDs, and the personal data the project
   classifies as sensitive. Never log request or response bodies wholesale;
   allowlist the fields you need.
5. **Metrics.** Use RED for request-driven work (rate, errors, duration) and USE
   for resources (utilization, saturation, errors): counters for events,
   histograms for latency and sizes, gauges for queue depth or pool use.
   - Follow the project's naming scheme. For Prometheus, use base units and
     suffixes (`_seconds`, `_bytes`, `_total` on counters). For OpenTelemetry
     metrics, use semantic-convention names such as
     `http.server.request.duration` (seconds).
   - Keep label cardinality bounded. Series per metric is roughly the product of
     each label's distinct values, multiplied across instances. Use route
     templates, methods, and status classes; never user IDs, request IDs, emails,
     raw URLs, or error messages. Keep within the project's series budget (for
     example, hundreds rather than tens of thousands per metric).
   - Put a histogram bucket boundary at the SLO latency threshold, so the share
     of requests within it can be computed exactly.
6. **Tracing.** Propagate W3C Trace Context (`traceparent`, `tracestate`) across
   HTTP and messaging boundaries; the OpenTelemetry default propagators do this.
   - Prefer instrumentation libraries for HTTP servers and clients, database
     drivers, and queues, and add manual spans only for meaningful I/O or
     business operations, not trivial helpers.
   - Name attributes by the OpenTelemetry semantic conventions:
     `http.request.method`, `http.route`, `http.response.status_code`,
     `server.address`, `error.type`, and the resource attributes `service.name`
     and `service.version`. Older instrumentation emits earlier names (for
     example `http.method`, `http.status_code`), and database names changed too.
     Match the version your SDK and instrumentation emit rather than mixing
     them; for migrations, check whether they support
     `OTEL_SEMCONV_STABILITY_OPT_IN`.
   - Put custom attributes under a project namespace (for example
     `billing.batch.size`). Never put credentials, personal data, or full URLs
     with query strings into attributes.
   - Keep span names low-cardinality (`GET /orders/{id}`, not the raw path). For
     HTTP, a server span is an error only on 5xx; a client span is an error on
     4xx and 5xx.
   - Sampling follows project policy: head sampling in the SDK (parent-based
     ratio) and, if the project runs a collector, tail sampling to keep errors
     and slow traces.
7. **Alerts.** Prefer symptom-based alerts on user-facing SLOs (error-budget
   burn rate) over cause-based ones (CPU, memory, restarts).
   - Every paging alert must be actionable, owned (team or routing label), have
     a severity, and link a runbook and dashboard.
   - Cause-based alerts become tickets or dashboards unless they predict
     imminent user impact (for example a disk filling within hours).
   - Deduplicate rules that fire on the same condition, and use recording rules
     for expensive ratios.

## Reference snippets (illustrative)

Python with the standard `logging` module, `prometheus_client`, and the
OpenTelemetry API; adapt to the project's libraries and names.

```python
import logging
import time

from opentelemetry import trace
from prometheus_client import Counter, Histogram

# The single redaction point. Attach the filter to every handler, because
# filters on a logger do not apply to records propagated from child loggers.
SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "cookie",
                  "session_id", "api_key", "email"}


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class RedactFilter(logging.Filter):
    def filter(self, record):
        for key, val in list(vars(record).items()):
            if key.lower() in SENSITIVE_KEYS:
                setattr(record, key, "[REDACTED]")
            elif isinstance(val, dict):
                setattr(record, key, redact(val))
        return True


SETTLEMENTS = Counter(  # exposed as billing_settlements_total
    "billing_settlements", "Settlement attempts by outcome.", ["outcome"])
SETTLE_SECONDS = Histogram(
    "billing_settlement_duration_seconds", "Time to settle one batch.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))

tracer = trace.get_tracer("billing.settlement")
log = logging.getLogger("billing.settlement")


def submit(invoices: list) -> str:
    """Project code; returns "succeeded" or "declined"."""
    raise NotImplementedError


def settle(batch_id: str, invoices: list) -> None:
    # start_as_current_span records exceptions and sets ERROR status by default.
    with tracer.start_as_current_span("settle invoice batch") as span:
        span.set_attribute("billing.batch.size", len(invoices))
        start = time.perf_counter()
        outcome = "error"
        try:
            outcome = submit(invoices)  # instrumented HTTP client adds child spans
        finally:
            SETTLE_SECONDS.observe(time.perf_counter() - start)
            SETTLEMENTS.labels(outcome=outcome).inc()  # bounded label values
            # IDs go to logs and span attributes, never to metric labels.
            log.info("settlement.finished",
                     extra={"batch_id": batch_id, "outcome": outcome})
```

A multiwindow burn-rate page for a 99.9% availability SLO over 30 days (error
budget 0.001). A burn rate of 14.4 spends 2% of the monthly budget in one hour;
requiring both the 1-hour and 5-minute windows makes it page fast and reset
fast. A slower pair (for example burn rate 6 over 6 hours and 30 minutes) catches
slower burns. Substitute the project's SLO, metric names, and labels.

```yaml
groups:
  - name: checkout-slo
    rules:
      - alert: CheckoutErrorBudgetFastBurn
        expr: |
          (
            sum(rate(checkout_http_requests_total{status_class="5xx"}[1h]))
            / sum(rate(checkout_http_requests_total[1h]))
          ) > (14.4 * 0.001)
          and
          (
            sum(rate(checkout_http_requests_total{status_class="5xx"}[5m]))
            / sum(rate(checkout_http_requests_total[5m]))
          ) > (14.4 * 0.001)
        labels:
          severity: page
          team: checkout
        annotations:
          summary: "Checkout is spending its 30-day error budget over 14x too fast"
          runbook_url: "https://runbooks.example.internal/checkout/error-budget-burn"
          dashboard: "https://grafana.example.internal/d/checkout-slo"
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never remove existing dashboards, alert rules, or exporter configuration
  you did not create.
- Ask before adding a telemetry dependency, a new destination or exporter, or
  changing paging routes. Never ship telemetry to an unapproved third party.
- No credentials, tokens, session IDs, or personal data in logs, metric labels,
  or span attributes; redaction lives in one place and has a test. No unbounded
  label values; IDs belong in logs and traces.
- Never weaken a test, check, or alert threshold to make work pass. Changing an
  existing threshold needs the owner's agreement and a reason in the report.
- Instrumentation on hot paths has a cost. If overhead could matter, measure it
  with the `performance-optimization` skill rather than guessing.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately; never chain alternatives with `||`.

- Type check, lint, and tests pass, including a test that logs sensitive fields
  (top-level and nested) through the configured handler and asserts that only
  `[REDACTED]` appears.
- Start the service locally, send a few requests, and scrape its metrics
  endpoint (for example `curl -s http://127.0.0.1:<port>/metrics`). Only the
  declared label names appear, and no label value looks like an ID, email, or
  token. Stop the service afterward.
- Traces: with a console exporter or local collector, one request across two
  services shares a trace ID, the parent and child links are correct, and the
  attribute names match the semantic conventions version in use.
- Alert rules: for Prometheus, `promtool check rules <file>` passes, and
  `promtool test rules <test-file>` passes when the project keeps rule tests.
  Every paging rule has an owner, severity, and runbook link.

## Report

- **Signals added:** log events, metric series with their labels, spans, and
  alert rules, each mapped to the operator question it answers.
- **Stack reused:** libraries, destinations, and the semantic conventions
  version followed.
- **Safeguards:** redacted fields and where redaction lives, label restrictions,
  and the estimated series count per new metric.
- **Alerts:** thresholds with their SLO source, owner, severity, and runbook
  link; runbooks still to be written.
- **Verification:** each command and its result.
- **Gaps and not verified:** areas still unobserved, overhead not measured, and
  checks that could not run.

## Optional delegation

The `performance-profiler` subagent can measure instrumentation overhead on a hot
path. The `runbook-writer` subagent can draft the runbook a new paging alert
links to. The `security-reviewer` subagent can review telemetry for sensitive
data exposure. One agent can complete this workflow alone.
