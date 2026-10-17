---
name: deployment-safety
description: "Plan and verify a staged rollout of a service change: preflight checks, canary cohorts, health gates with abort thresholds, a rehearsed rollback, and a verification report. Use when preparing or executing a deploy, canary, blue-green, or rollback plan. Every environment change, staging included, needs explicit approval. Not for database migration plans (use the safe-migration skill) or active incidents (use the incident-triage skill)."
---

# Deployment Safety

Prepare a change so it can be released deliberately, observed at every step,
and reversed quickly. The stance is **plan first, mutate only with approval**:
the agent drafts the plan and runs read-only checks; every command that changes
an environment, including staging rollback drills, runs only after the user
explicitly approves it.

## When to use

- Planning a production (or staging) release, canary, blue-green switch, or
  rolling update.
- Defining health gates, abort thresholds, halt authority, and rollback steps.
- Executing an approved rollout stage by stage and recording the evidence.

## When not to use

- Schema or data changes need a rollout plan: use the `safe-migration` skill or
  delegate to the `migration-planner` subagent, then reference that plan here.
- Production is already broken: use the `incident-triage` skill.
- Mobile app store or OTA releases: use the `mobile-release-safety` skill.
- Pre-merge checks for a change: use the `verify-and-ship` skill.
- Release readiness audit: delegate to the `release-engineer` subagent.
- Adding, rolling out, or removing feature flags and kill switches: use the
  `feature-flag-lifecycle` skill.
- Changing the infrastructure itself: use the `infrastructure-as-code` skill.

## Inputs to gather

Discover these before asking; ask only what remains ambiguous.

- The artifact (image, package, bundle), the commit it was built from, and its
  immutable digest from CI output.
- Target environment, deployment platform and tooling (Kubernetes with or
  without a progressive-delivery controller, serverless, VMs, PaaS), and the
  project's deploy commands from `AGENTS.md`, runbooks, or CI.
- What changed: code, configuration, feature flags, migrations, dependencies.
- Health signals and where they live (metrics, logs, traces, dashboards), and
  the project's SLOs or alert thresholds.
- Release policy: approvals, maintenance windows, who may halt a rollout.
- Who executes (operator) and who watches signals (observer).

## Workflow

1. **Define the change.** Owner, target environment, blast radius (services,
   downstream consumers, shared databases, queues, caches), and success and
   abort criteria as measurable statements: "canary 5xx rate stays below the
   SLO for 30 minutes", never "looks healthy".
2. **Verify the artifact and preconditions.** The digest matches the CI build
   for the commit. Tests are green at that commit. Migrations are reviewed and
   backward compatible (expand and contract) while old and new versions
   overlap. Risky behavior sits behind a flag that defaults off. Required
   approvals are recorded.
3. **Check the environment.** Diff configuration between source and target
   environments; unexplained deltas block the rollout. Confirm runtime
   versions, dependency availability, secret references (by name only),
   permissions, and capacity headroom.
4. **Write the staged plan** (see the example): preflight, a small cohort,
   observation windows, expansion, completion. One person should not be both
   operator and observer for production unless the plan says so explicitly.
5. **Bind each gate to a query** the observer runs verbatim. Scope canary
   signals to the canary (a version or track label) and compare against the
   stable baseline: a fleet-wide rate at 5% traffic hides a badly failing
   canary. Treat a missing or empty signal as a failed gate.
6. **Set abort thresholds and halt procedure.** Use the project's SLOs; for
   example a 5xx rate above 1% or p95 latency above 500 ms. Halting freezes
   expansion and preserves logs, metric snapshots, and deployment state before
   any restart.
7. **Define rollback and forward fix.** Know what a rollback does not revert.
   For example, `kubectl rollout undo` restores only the previous pod template;
   ConfigMaps, Secrets, migrations, flags, and messages already written stay as
   they are. Document data compatibility both ways and a forward-fix path for
   when rollback is unsafe.
8. **Propose a staging rollback drill.** Present the exact drill commands and
   run them only after approval. Record the measured time back to baseline.
9. **Get explicit approval for the production scope**, then execute one stage
   at a time. At each gate, run the gate checks, record timestamps and values,
   and stop at the first failed gate: halt, preserve evidence, and propose the
   rollback. Expanding beyond the approved scope needs new approval. Do not
   improvise new actions mid-rollout.
10. **Write the verification report** (see Report).

## Example: staged rollout plan

Illustrative values; take thresholds from the project's SLOs.

```yaml
release:
  artifact: registry.example.com/checkout-service
  revision: 9f3a2c1d4e5f60718293a4b5c6d7e8f901234567
  digest: sha256:<digest-from-ci>
  environment: production
  change: "Idempotent payment retry behind flag payment_retry_v2 (default off)"
  blast_radius: "checkout-service pods; payments Postgres (read-only access)"
approvals:
  code_review: "PR 4821 approved"
  migration_review: "not required: no schema change"
preflight:
  - digest matches the CI build for the revision
  - unit, integration, and contract tests green at the revision
  - staging versus production config diff has no unexplained deltas
  - flag payment_retry_v2 exists and defaults to off
  - capacity headroom meets policy (for example 30% CPU and pool)
rollout:
  operator: <operator>
  observer: <observer>
  stages:
    - { name: canary-5, traffic_percent: 5, observe_minutes: 30, gates: [error_rate, latency_p95, dependency_health] }
    - { name: canary-25, traffic_percent: 25, observe_minutes: 30, gates: [error_rate, latency_p95, checkout_ratio] }
    - { name: full, traffic_percent: 100, observe_minutes: 60, gates: [error_rate, latency_p95, saturation, checkout_ratio] }
signals: # scoped to the canary track; compare with track="stable"
  error_rate: 'sum(rate(http_requests_total{app="checkout",track="canary",status=~"5.."}[5m])) / sum(rate(http_requests_total{app="checkout",track="canary"}[5m]))'
  latency_p95: 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{app="checkout",track="canary"}[5m])))'
  checkout_ratio: 'sum(rate(checkout_completed_total[10m])) / sum(rate(checkout_completed_total[10m] offset 1w))'
abort_thresholds:
  error_rate_max: 0.01
  latency_p95_max_seconds: 0.5
  checkout_ratio_min: 0.95
halt:
  authority: [<operator>, <observer>, <on-call lead>]
  procedure:
    - freeze traffic weight; do not expand
    - snapshot metrics, logs, and pod state before any restart
    - notify the halt authority with the evidence
rollback:
  steps:
    - disable flag payment_retry_v2  # requires approval
    - kubectl -n production rollout undo deployment/checkout-service  # requires approval
    - kubectl -n production rollout status deployment/checkout-service --timeout=600s
    - confirm error_rate and latency_p95 back at baseline
  not_reverted_by_rollback: "ConfigMaps, Secrets, flags, rows written by the new version"
  data_compatibility: "no schema change; old code tolerates rows written by new code"
  forward_fix: "if rollback breaks queue consumers, ship a compatibility hotfix"
```

With a progressive-delivery controller, use its commands for expansion and
halting instead (for example `kubectl argo rollouts promote checkout-service`
or `kubectl argo rollouts abort checkout-service` with Argo Rollouts), each
with approval. A plain Kubernetes Deployment cannot split traffic by
percentage on its own.

## Gate check (read-only)

Run at every stage gate. It exits non-zero when the gate fails, including when
the signal is missing.

```bash
set -euo pipefail
NS=production; DEPLOY=checkout-service; MAX=0.01
PROM_URL="${PROM_URL:?set to the metrics query endpoint}"

kubectl -n "$NS" rollout status "deployment/$DEPLOY" --timeout=300s
curl -fsS -o /dev/null -w 'healthz status=%{http_code} time=%{time_total}s\n' \
  https://api.example.com/healthz

RATE=$(curl -fsS "$PROM_URL/api/v1/query" \
  --data-urlencode 'query=sum(rate(http_requests_total{app="checkout",track="canary",status=~"5.."}[5m])) / sum(rate(http_requests_total{app="checkout",track="canary"}[5m]))' \
  | jq -r '.data.result[0].value[1] // empty')
case "$RATE" in
  ""|NaN|+Inf|-Inf) echo "GATE FAIL: no usable error-rate sample: '$RATE'"; exit 1 ;;
esac
if awk -v r="$RATE" -v max="$MAX" 'BEGIN { exit !(r + 0 < max + 0) }'; then
  echo "GATE PASS: error_rate=$RATE"
else
  echo "GATE FAIL: error_rate=$RATE is at or above $MAX; halt"
  exit 1
fi
```

Staging rollback drill, proposed to the user and run only after approval:

```bash
CANDIDATE="${CANDIDATE:?set to the candidate image reference with its digest}"
kubectl -n staging set image deployment/checkout-service app="$CANDIDATE"  # requires approval
kubectl -n staging rollout status deployment/checkout-service --timeout=600s
kubectl -n staging rollout undo deployment/checkout-service  # requires approval
kubectl -n staging rollout status deployment/checkout-service --timeout=600s
```

Record the start and end time of the undo and the time until the gate check
passes again.

## Guardrails

- Revert or delete only files you created or changed in this session. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Here that means every environment mutation: deploys, traffic shifts, flag
  changes, scaling, restarts, rollbacks, and drills, in any environment.
- Never weaken a gate, raise a threshold mid-rollout, or skip an observation
  window to keep a rollout moving.
- Never assume a schema rollback is safe; verify compatibility or document the
  forward fix.
- Keep secrets out of plans, logs, and reports. Reference them by name or
  vault path only. Redact tokens, session IDs, and customer data from evidence.

## Verification

Use the project's own commands, run separately.

1. Artifact traceability: the running or candidate image digest matches the CI
   build output for the commit (for example
   `kubectl -n production get deployment checkout-service -o jsonpath='{.spec.template.spec.containers[0].image}'`).
2. The project's test command passes at the release commit.
3. The gate check passes at each stage, with recorded values and timestamps.
4. If a drill was approved and run, the measured time back to baseline is
   within the target the project sets.
5. The plan and report contain no secret values:
   `grep -nEi '(password|token|secret|api[_-]?key)[[:space:]]*[:=]' rollout-plan.yaml`
   prints nothing, or each hit is a reference by name.

## Report

Return the plan, then a verification report. Save it where the project keeps
release records (for example `docs/releases/`), or return it in the reply if
there is no convention.

<!-- handoff: verification-report -->
```markdown
# Verification report: <service> <revision> to <environment>

## Scope

Artifact, digest, revision, environments, stages approved and executed, and
who approved them.

## Commands and results

Each preflight and gate command with timestamp, observed value, threshold,
and PASS or FAIL. Drill commands and measured time back to baseline.

## Evidence

Links or paths to metric snapshots, logs, and rollout history (redacted).

## Limitations

Signals not available, stages not executed, and anything not verified.

## Handoff

**Changed contract:** behavior or configuration that changed for users or consumers.
**Files / systems affected:** services, environments, flags, and data stores.
**Evidence and tests:** tests at the revision and gate results per stage.
**Risks / rollback:** open risks, rollback steps, and what rollback does not revert.
**What the next agent needs:** current stage, pending approvals, next action.
```

## Optional delegation

The `release-engineer` subagent can audit release readiness and the change
set in parallel. The `migration-planner` subagent can check migration
compatibility. The `infrastructure-reviewer` subagent can review manifests
touched by the release. One agent can complete this workflow alone.
