---
name: write-runbook
description: "Write or update an operational runbook for one failure mode of a service, with detection, diagnosis, mitigation, recovery, and escalation steps extracted from code, configuration, alerts, and drill evidence. Use when a service, alert, or failure mode has no runbook, an existing runbook is stale or untested, or a postmortem asks for one. Not for coordinating a live incident (use the incident-triage skill) or general documentation (use the write-documentation skill)."
---

# Write Runbook

Produce a runbook that an on-call engineer can follow under pressure for one
failure mode. The stance is **extract, never invent**: every command, threshold,
path, and owner traces to code, configuration, infrastructure definitions, or
drill evidence, and anything without evidence is a visible gap. This skill
documents procedures; it never runs them against production.

## When to use

- A service, alert, or failure mode has no runbook, or alerts link to nothing.
- An existing runbook is stale, untested, or contradicted by the current code.
- A postmortem action item asks for a runbook.

## When not to use

- An incident is happening now: use the `incident-triage` skill, and write the
  runbook afterward.
- Alerts or instrumentation are missing or wrong: use the `observability-setup`
  skill, then link the runbook from the alert.
- The procedure is a rollout or rollback of a change: use the
  `deployment-safety` skill.
- READMEs, how-to guides, or reference docs: use the `write-documentation` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the runbook.

- The service and the single failure mode. If the request names several, plan
  one runbook per mode.
- The owning team, from `CODEOWNERS`, a service catalog file, or deployment
  annotations. If it is not discoverable, write `owner: unknown` and flag the
  gap; never invent a team.
- Signals: alert rule files (Prometheus or Alertmanager rules, Grafana
  provisioning, paging-service definitions kept as code), dashboards, log
  sources, and health endpoints.
- Operational interfaces: deploy manifests, feature flags, admin endpoints, and
  operational scripts, plus the commands they imply.
- Existing runbooks (their location, format, and naming), postmortems, and
  incident timelines.
- The authority model: who may run which kind of action (on-call, team lead,
  DBA, incident commander), and how secrets are retrieved (secret manager path
  or role).

## Workflow

1. **Scope one failure mode.** Name it concretely, for example "orders-api
   connection pool exhaustion". Check existing runbooks so you do not duplicate
   one; link sibling runbooks that cover lookalikes. Write for the primary
   on-call engineer, not the system designer.
2. **Map evidence.** For each claim you will make, note the file or system that
   proves it. Commands come from scripts, manifests, documented interfaces, or
   past incident timelines. Where evidence is missing, write a marked gap such
   as `GAP: no alert covers this mode; proposed follow-up: ...` instead of
   plausible prose.
3. **Detection.** List the exact alert names with their rule file paths, metric
   expressions, dashboard panels, and log queries, in the order an operator
   should look. For each lookalike failure mode, give the observation that
   tells them apart and the sibling runbook that owns it. If no alert exists,
   say so and recommend one; never fabricate an alert name.
4. **Diagnosis.** Order checks cheapest and least invasive first, read-only
   before anything else. Each check has the exact command or query, the
   expected healthy output, the expected failing output, and the authority
   needed to run it. Tell the operator to stop when one check confirms.
5. **Mitigation.** Order steps from least to most invasive, reducing user
   impact first. Each step has:
   - the command or action;
   - the expected effect (what improves, and how fast if evidence says so);
   - the abort condition that means stop this step;
   - the authority required;
   - how to reverse it.

   Steps that destroy data, restart stateful infrastructure, drop traffic, or
   change network policy also get a pre-check and require elevated authority.
6. **Recovery.** Reverse each mitigation, then verify with commands and expected
   output that show the service is healthy, not merely quiet. Define the watch
   period and the closing criterion, taken from the project's SLO when one
   exists.
7. **Escalation.** State when escalation is mandatory (a time box or a failed
   step count from team policy; mark it a gap if none exists), to whom in order,
   through which channel, and the snapshot to hand over: metrics, command
   outputs, steps already taken, and time since detection.
8. **Label and header.** The header carries service, failure mode, owner,
   status, last tested date, drill cadence, and review trigger. Mark every step
   not yet executed end to end in staging, a drill, or a real incident as
   `UNTESTED` inline. Any untested step makes the status `DRAFT`.
9. **Save and link.** Save the runbook where the project keeps runbooks (for
   example `docs/runbooks/`), following its naming and format. If alert rules
   live in the repository, propose adding the runbook link to the alert's
   annotation; ask before editing alert rules owned by another team.

## Worked example (illustrative)

Condensed runbook for one failure mode. Names, numbers, and commands are
examples; a real runbook takes each from evidence.

```markdown
# Runbook: orders-api connection pool exhaustion

- Service: `orders-api` | Owner: `team-payments` | Status: DRAFT (mitigation 3 untested)
- Last tested: 2026-07-20, staging drill | Drill cadence: quarterly
- Review after: any incident in this mode, or a change to pool settings

## Detection
- Alert `OrdersApiPoolSaturation` (`alerts/orders-api.yaml`): pool active/max above 0.9 for 5 minutes.
- Dashboard `orders-api-db`, panels "Pool utilization" and "Checkout wait".
- Lookalikes:
  - Slow queries: pool use below 50% but query p99 high. See runbook `orders-api-slow-queries`.
  - Database down: `pg_isready -h <db-host>` exits non-zero. See runbook `postgres-failover`.

## Diagnosis (cheapest first; stop when one confirms)
1. Pooler state. Authority: on-call.
   `psql "<pgbouncer admin DSN from secret manager: orders/pgbouncer>" -c "SHOW POOLS;"`
   - Healthy: `cl_waiting` is 0.
   - Failing: `cl_waiting` above 0 and growing; `sv_active` at the pool size.
2. Session states. Authority: on-call.
   `psql "<orders admin DSN>" -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'orders' GROUP BY state;"`
   - Healthy: mostly `idle`; `active` well below `max_connections`.
   - Failing: many `idle in transaction` sessions.

## Mitigation (least invasive first)
1. Terminate sessions idle in a transaction for over 5 minutes. Authority: on-call.
   - Pre-check: run the same filter as a SELECT of `pid, usename, xact_start`.
     If any row belongs to the migration role, stop and escalate to the DBA.
   - Command: `psql "<orders admin DSN>" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'orders' AND state = 'idle in transaction' AND now() - xact_start > interval '5 minutes';"`
   - Expected effect: `cl_waiting` returns to 0 within about 2 minutes; 5xx rate falls.
   - Abort: no change in 5xx rate after 5 minutes; move to step 2.
   - Reverse: not needed; clients reconnect.
2. Shed writes with the read-only flag. Authority: on-call.
   - Command: `kubectl -n orders set env deploy/orders-api ORDERS_READ_ONLY=1` (rolling restart)
   - Expected effect: writes return 503 with `Retry-After`; pool use roughly halves.
   - Abort: 5xx above 5% after the rollout; set `ORDERS_READ_ONLY=0`.
   - Reverse: recovery step 2.
3. Restart the pooler. Authority: team-payments lead. UNTESTED.
   - Command: `kubectl -n orders rollout restart deploy/pgbouncer`
   - Expected effect: server connections re-established; utilization resets.
   - Abort: rollout incomplete after 5 minutes; escalate to the DBA on-call.

## Recovery
1. Pool utilization below 60% for 10 minutes on the dashboard.
2. `kubectl -n orders set env deploy/orders-api ORDERS_READ_ONLY=0`, then
   `kubectl -n orders rollout status deploy/orders-api`.
   - Healthy: `deployment "orders-api" successfully rolled out`.
3. Synthetic write probe:
   `curl -sS -o /dev/null -w "%{http_code}\n" -X POST "https://<internal-host>/api/orders/synthetic" -H "Authorization: Bearer <probe token from secret manager>"`
   - Healthy: `201`. Failing: any 5xx.
4. Close when the error-budget burn rate stays below 1 for 30 minutes.

## Escalation
| Condition                              | Escalate to        | Channel          | Provide                       |
|----------------------------------------|--------------------|------------------|-------------------------------|
| Steps 1-2 ineffective after 15 minutes | team-payments lead | page             | pool and session snapshots    |
| A pre-check or abort condition is hit  | DBA on-call        | page             | pid list, migration status    |
| Suspected data loss                    | incident commander | incident channel | timeline, affected order ids  |

Every escalation includes the current 5xx rate, pool utilization, steps run with
their outputs, and minutes since detection.
```

## Guardrails

- Document, never execute. Do not run the runbook's commands against
  production or any shared environment, apply configuration, or connect to live
  systems while writing it. Testing a step is a drill that the owning team
  schedules and approves.
- Extract, never invent. A command, threshold, path, alert, or owner without
  evidence is written as a gap, not as fact.
- One failure mode per runbook. Link lookalikes instead of merging them.
- Untested means labeled: inline `UNTESTED` on the step and `Status: DRAFT` in
  the header, never a footnote.
- No credentials, tokens, passwords in connection strings, or private keys.
  Reference the secret manager by path or role. Replace internal hostnames and
  bypass flags with placeholders if the runbook may leave the trust boundary
  (public repository, vendor ticket, chat export).
- Every step that can destroy data or drop traffic carries a risk note, a
  pre-check, and its elevated authority.
- Revert or delete only files you created or changed in this session. Ask
  before editing alert rules, dashboards, or runbooks owned by another team.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately; never chain alternatives with `||`.

- Every diagnosis step has a command, healthy output, failing output, and an
  authority. Every mitigation step has an expected effect, abort condition,
  authority, and reversal.
- Every `UNTESTED` step is matched by `Status: DRAFT` in the header (search the
  file for both strings).
- Every repository path and alert name cited exists (search the rule files for
  each alert name).
- Shell snippets parse: copy them to a file in a temporary directory outside the
  repository and run `bash -n` on it. Quote placeholders first, since a bare
  `<placeholder>` parses as a redirect. Never execute the snippets.
- The project's markdown linter and secret scanner pass, if it has them.

## Report

- **Runbook:** path, service, failure mode, owner, and status with its reason.
- **Lookalikes:** the failure modes it distinguishes and the sibling runbooks it
  links.
- **Evidence:** the source for each section, and every gap left open.
- **Untested steps:** the list, and a proposed drill to test them.
- **Follow-ups:** missing alerts or owners, drill cadence, review triggers, and
  automation worth adding (for example a synthetic probe).
- **Not verified:** checks that could not run and why.

## Optional delegation

The `runbook-writer` subagent can draft the runbook from repository evidence
and return it as text; check every command and claim against its cited evidence
before you save it. The `explorer` subagent can inventory alert rules, dashboards,
and operational scripts in parallel. One agent can complete this workflow alone.
