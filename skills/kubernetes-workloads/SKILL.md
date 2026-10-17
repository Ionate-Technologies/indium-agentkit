---
name: kubernetes-workloads
description: "Write or change Kubernetes manifests, Helm charts, or Kustomize overlays for a workload: measured requests and limits, safe startup, readiness, and liveness probes, disruption budgets, autoscaling bounds, graceful rollout and shutdown, a restricted security context, minimal RBAC, network policies, external secrets, and digest-pinned images, validated by rendering and server-side dry run. Use when deploying a service, worker, or cron job to Kubernetes or changing its manifests or chart. Not for Dockerfiles (use the containerize-service skill) or reviews (use the infrastructure-review skill)."
---

# Kubernetes Workloads

Describe a workload so it schedules predictably, survives rollouts, node drains,
and load spikes, and runs with the least privilege it needs. The stance is
**render and dry-run, apply only with approval**: every value comes from
measurement or the application's real behavior, and nothing reaches a cluster
until the user approves it.

## When to use

- Deploying a service, worker, or cron job to Kubernetes, or changing its
  Deployment, StatefulSet, CronJob, Service, Ingress, autoscaler, disruption
  budget, RBAC, or network policy.
- Writing or changing a Helm chart or its values, or Kustomize bases and overlays.
- Pods are OOMKilled, CPU-throttled, restarted by probes, dropping requests
  during rollouts, or blocking node drains.

## When not to use

- Building the container image: use the `containerize-service` skill.
- The cluster, node pools, or cloud IAM in Terraform or similar: use the
  `infrastructure-as-code` skill.
- Reviewing manifests: use the `infrastructure-review` skill, or delegate to the
  `infrastructure-reviewer` subagent.
- Rolling the change out with canaries and health gates: use the
  `deployment-safety` skill. An active incident: use the `incident-triage` skill.
- How the application reads configuration and secrets: use the
  `config-and-secrets` skill.

## Inputs to gather

Discover these from the repository and cluster documentation first. Ask only
about what remains ambiguous.

- How manifests are managed: raw YAML, Helm (chart plus values per
  environment), Kustomize (base plus overlays), and whether a GitOps controller
  (Argo CD, Flux) syncs from git. With GitOps, merging to the tracked branch is
  the deploy, so the merge is the approval point.
- Cluster versions and policy: Pod Security admission labels on the namespace,
  policy engines (Kyverno, Gatekeeper), LimitRange and ResourceQuota, whether
  the CNI enforces NetworkPolicy, the ingress controller, the secrets operator,
  and any service mesh.
- Application behavior: ports, health endpoints, startup time, what it does on
  `SIGTERM` and how long draining takes, writable paths, whether it calls the
  Kubernetes API, and its outbound destinations.
- Measured CPU and memory: Prometheus, `kubectl top pod` (needs metrics-server),
  load-test results, or Vertical Pod Autoscaler recommendations.
- Which non-production cluster, context, and namespace you may dry-run against.

## Workflow

1. **Follow the existing structure.** Reuse chart helpers, label templates,
   values layout, and overlays; prefer a values or overlay change to a forked
   template.
2. **Size requests and limits from measurement.**
   - Requests are what the scheduler reserves. Set CPU and memory requests from
     observed usage at typical load plus headroom, per the team's policy (for
     example p95 usage plus 20%).
   - A container that exceeds its memory limit is OOMKilled. Set the limit from
     observed peak plus headroom; many teams set it equal to the request.
   - A container that exceeds its CPU limit is throttled, which raises latency
     even when the node has idle CPU. Common choices are a CPU request with no
     limit, or a limit well above the request; follow cluster policy, since a
     LimitRange may impose one. Guaranteed QoS needs requests equal to limits
     for CPU and memory in every container.
   - Match runtime settings to the container: JVM `-XX:MaxRAMPercentage`,
     Node.js `--max-old-space-size`, Go `GOMEMLIMIT`, and worker counts.
   - Without measurements, start from a load test or a similar service, mark
     the values provisional in the report, and plan a review.
3. **Write probes that cannot cause an outage.**
   - `startupProbe` for slow starts: liveness and readiness wait until it
     succeeds. Make `failureThreshold` times `periodSeconds` cover the slowest
     observed start.
   - `readinessProbe` answers "can this pod take traffic now?" and removes the
     pod from Service endpoints while failing. If it checks a dependency that
     every pod shares, an outage of that dependency empties the Service; decide
     that deliberately.
   - `livenessProbe` answers "is this process stuck?" and restarts the
     container. Check only the process itself, never a database, cache, or
     downstream API: a dependency outage would restart every pod.
   - Probe handlers must be cheap and must not queue behind request work. The
     default `timeoutSeconds` is 1; under load, a slow liveness check kills
     busy, healthy pods and makes the overload worse. Give liveness a generous
     `failureThreshold` and keep it less aggressive than readiness.
4. **Roll out and shut down gracefully.**
   - `strategy.rollingUpdate` with `maxUnavailable: 0` and `maxSurge: 1` (or a
     percentage) keeps capacity during rollouts if quota allows the extra pod.
   - Omit `spec.replicas` when a HorizontalPodAutoscaler manages the workload;
     otherwise every apply resets the replica count.
   - Endpoint removal and `SIGTERM` happen at about the same time, so traffic
     can still arrive briefly. Add a short `preStop` delay (an `exec` of
     `sleep`, which needs a `sleep` binary in the image, or the built-in sleep
     action on recent Kubernetes versions; check yours), make the application
     finish in-flight work on `SIGTERM`, and set `terminationGracePeriodSeconds`
     (default 30) to cover the delay plus the longest drain.
   - `spec.selector` is immutable. Select only on stable labels (name,
     instance), never on version; changing a selector means recreating the
     workload, which needs approval.
5. **Stay available through disruption.**
   - Run at least two replicas for anything that must stay up, per policy.
   - Add a PodDisruptionBudget, for example `maxUnavailable: 1`. A budget that
     allows zero disruptions (one replica with `minAvailable: 1`) blocks node
     drains and upgrades. Budgets cover evictions, not rolling updates or crashes.
   - HorizontalPodAutoscaler (`autoscaling/v2`): `minReplicas` meets the
     availability need; `maxReplicas` respects quota and downstream limits such
     as database connections per pod times pods. CPU utilization targets are a
     percentage of the request, so requests must be set.
   - Spread replicas across zones and nodes with `topologySpreadConstraints`
     (`topology.kubernetes.io/zone`, `kubernetes.io/hostname`), or preferred
     pod anti-affinity.
6. **Restrict the security context.** The Pod Security restricted profile
   requires `runAsNonRoot: true` (use a numeric `runAsUser`; the kubelet cannot
   verify a named image user), `seccompProfile.type: RuntimeDefault`,
   `allowPrivilegeEscalation: false`, and `capabilities.drop: ["ALL"]`, adding
   back at most `NET_BIND_SERVICE`. Also set `readOnlyRootFilesystem: true` with
   `emptyDir` mounts for writable paths. No `privileged`, host namespaces, or
   `hostPath` without approval.
7. **Give it its own identity.** A dedicated ServiceAccount, with
   `automountServiceAccountToken: false` unless the application calls the API.
   A namespaced Role and RoleBinding with named resources and verbs, no
   wildcards, and no cluster-wide binding unless required; note that `list` on
   Secrets returns their contents. Reach cloud APIs through workload identity
   annotations, not mounted keys.
8. **Restrict the network.** If the namespace has no default-deny NetworkPolicy,
   add one with the change owner's agreement, then allow ingress from named pods
   or namespaces on named ports and egress to named destinations, including DNS
   (port 53 over UDP and TCP). Confirm the CNI enforces policies; otherwise they
   do nothing.
9. **Separate configuration from secrets.** Use ConfigMaps for configuration
   and Secrets supplied by the project's mechanism (External Secrets Operator,
   Sealed Secrets, SOPS, or a CSI secrets driver). Never commit a plain Secret
   manifest (base64 is encoding, not encryption) or secret values in Helm
   values. Pods do not restart when these change: mounted volumes update after
   a delay, while environment variables and `subPath` mounts never update. If
   the application reads configuration only at startup, roll pods with a checksum
   annotation in Helm,
   `checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}`,
   or a Kustomize generator's name suffix.
10. **Pin and label.** Reference the image by digest from CI output
    (`registry.example.com/app@sha256:...`), never `latest` or a bare tag. Use
    the `app.kubernetes.io/` labels (`name`, `instance`, `version`, `component`,
    `part-of`, `managed-by`) plus the owner labels the cluster policy requires.
11. **CronJobs and Jobs:** set `concurrencyPolicy` (usually `Forbid`),
    `startingDeadlineSeconds`, `backoffLimit`, and `activeDeadlineSeconds`; for
    idempotent handlers, use the `background-jobs-and-queues` skill.
12. **Validate and show the diff** (see Verification), then ask before any apply.

## Worked example: Deployment and disruption budget (illustrative)

Values come from measured usage and a service that drains within 30 seconds.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels: { app.kubernetes.io/name: orders-api, app.kubernetes.io/instance: orders-api }
spec:
  # No replicas field: the HorizontalPodAutoscaler owns the count.
  selector:
    matchLabels: { app.kubernetes.io/name: orders-api, app.kubernetes.io/instance: orders-api }
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    metadata:
      labels:
        app.kubernetes.io/name: orders-api
        app.kubernetes.io/instance: orders-api
        app.kubernetes.io/version: "1.4.2"
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 45   # 5 s preStop + 30 s drain + margin
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile: { type: RuntimeDefault }
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels: { app.kubernetes.io/name: orders-api, app.kubernetes.io/instance: orders-api }
      containers:
        - name: app
          image: registry.example.com/orders-api@sha256:<digest-from-ci>
          ports: [{ name: http, containerPort: 8080 }]
          resources:
            requests: { cpu: 250m, memory: 384Mi }   # measured p95: 190m, 310Mi
            limits: { memory: 384Mi }                # no CPU limit, per cluster policy
          startupProbe:
            httpGet: { path: /healthz, port: http }
            periodSeconds: 5
            failureThreshold: 24                     # up to 120 s to start
          readinessProbe:
            httpGet: { path: /ready, port: http }
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet: { path: /healthz, port: http }  # process only, no dependency checks
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 6
          lifecycle:
            preStop:
              exec: { command: ["sleep", "5"] }      # needs sleep in the image
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: { drop: ["ALL"] }
          volumeMounts: [{ name: tmp, mountPath: /tmp }]
      volumes: [{ name: tmp, emptyDir: {} }]
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api
spec:
  maxUnavailable: 1
  selector:
    matchLabels: { app.kubernetes.io/name: orders-api, app.kubernetes.io/instance: orders-api }
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  `kubectl apply`, `create`, `delete`, `patch`, `scale`, `rollout restart`, or
  `rollout undo`, and `helm install`, `upgrade`, `rollback`, or `uninstall`, in
  any cluster. Mark such lines `# requires approval`. With GitOps, ask before
  pushing or merging to a tracked branch.
- Check `kubectl config current-context` before every cluster command and pass
  `--context` explicitly; never dry-run or diff against production unless the
  user allows it.
- Deleting a StatefulSet, PersistentVolumeClaim, or namespace can destroy data;
  changing immutable fields (selectors, `volumeClaimTemplates`) forces a
  recreate. Plan these with the user.
- Never commit Secret values, kubeconfig files, or tokens, and never print
  Secret contents.
- Never raise limits, loosen probes, or disable a policy to hide a failure you
  have not diagnosed, and never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, the `Makefile`,
or CI. Run each check separately and report its real result; never chain
alternatives with `||`. Illustrative, with rendered output outside the repository:

```bash
OUT="$(mktemp -d)"
helm lint ./charts/orders-api -f ./charts/orders-api/values-staging.yaml
helm template orders-api ./charts/orders-api -f ./charts/orders-api/values-staging.yaml --namespace orders > "$OUT/rendered.yaml"
kubectl kustomize overlays/staging > "$OUT/rendered.yaml"    # Kustomize projects instead of Helm
kubeconform -strict -summary -kubernetes-version 1.30.0 "$OUT/rendered.yaml"
kube-linter lint "$OUT/rendered.yaml"
kubectl --context staging -n orders apply --dry-run=server -f "$OUT/rendered.yaml"
kubectl --context staging -n orders diff -f "$OUT/rendered.yaml"
kubectl --context staging -n orders apply -f "$OUT/rendered.yaml"   # requires approval
```

Set `-kubernetes-version` to the cluster's version; custom resources need their
schemas, or kubeconform's `-ignore-missing-schemas`. Flags differ across
versions; check `<tool> --help`.

- The chart or overlay renders for every environment, with no `latest` images
  and no plain Secret values in the output.
- Schema validation, linters, and the server-side dry run pass, including
  admission policies; `kubectl diff` shows only the intended changes.
- After an approved apply, `kubectl rollout status` completes, pods become
  ready, and `kubectl auth can-i --list` for the ServiceAccount (with
  `--as=system:serviceaccount:NAMESPACE:NAME`) shows only intended permissions.

## Report

- **Workload:** kind, namespace, environments, and how manifests are managed.
- **Sizing:** requests and limits, the measurements behind them, and whether
  they are provisional.
- **Availability:** probes, rollout strategy, grace period and `preStop`,
  disruption budget, autoscaler bounds, and spread.
- **Security:** security context, ServiceAccount and RBAC, network policies,
  secrets mechanism, and image digest.
- **Verification:** each command and its result, and the rendered diff.
- **Apply status:** not applied, or what was applied where after whose approval.
- **Not verified:** clusters or environments not checked, runtime behavior
  under load, and why.

## Optional delegation

The `infra-builder` subagent can implement a bounded manifest or chart change
and return the rendered diff. The `infrastructure-reviewer` subagent can review
the manifests independently; re-check its findings before acting. The workflow
above stays complete for a single agent.
