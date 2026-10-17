---
name: load-testing-suite
description: "Design and run load, stress, spike, and soak tests with k6, Locust, or the project's tool against an approved non-production target, using open-model arrival rates, SLO-based thresholds, and resource monitoring to find capacity limits. Use when validating throughput or latency targets, sizing capacity, or checking behavior under a traffic surge before a launch. Not for profiling one slow path (use the performance-optimization skill) or diagnosing a slow query (use the query-optimization skill)."
---

# Load Testing Suite

Measure how a system behaves under a stated workload, and find where it breaks,
without harming anything shared. The stance is **safe target, honest workload,
SLO-based verdict**: approval before load, arrival rates that do not hide slow
responses, and pass or fail judged against the project's own SLOs.

## When to use

- Check that a service meets its latency and error SLOs at the expected peak
  request rate.
- Find the breaking point and the first saturated resource before a launch or a
  traffic event.
- Check autoscaling and recovery under a spike, or leaks under a long soak.
- Confirm a performance fix holds under realistic load.

## When not to use

- One known slow endpoint or function: use the `performance-optimization` skill.
- A slow query or plan regression: use the `query-optimization` skill.
- A production rollout or canary: use the `deployment-safety` skill.
- Reviewing timeout, retry, and circuit-breaker policy: delegate to the
  `resilience-reviewer` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The target environment, and written approval for it. Local, a dedicated
  performance environment, or an approved staging slot. Never production or a
  shared environment without written approval.
- SLOs: latency percentiles, error rate, and expected peak rate, from SLO docs or
  alert rules. If none exist, ask; do not invent them.
- Traffic model: endpoints and their mix, payload variety, and auth, from access
  logs, analytics, or the API specification.
- Existing load tool and scripts in the repository (k6, Locust, Gatling, JMeter,
  or others). Reuse them.
- External dependencies to mock or sandbox: payment, email, SMS, and other
  third-party APIs.
- Test data: how to create isolated accounts and records, and how to remove them.
- Monitoring for the target: CPU, memory, GC pauses, connection pools, queue
  depth, and database load.

## Workflow

1. **Get approval and scope.** Confirm the target, time window, and peak rate in
   writing when the environment is not yours alone. Tell the owners of any
   shared dependency in the request path.
2. **Pick the test type.** Load (hold expected peak), stress (ramp past peak to
   find the knee), spike (sudden jump, then recovery), or soak (moderate load for
   hours to expose leaks).
3. **Pick the load model.**
   - When the goal is a target request rate, use an open model: k6
     `constant-arrival-rate` or `ramping-arrival-rate`. New iterations start on
     schedule whatever the response time, so a slowdown shows up as latency
     instead of silently reducing load.
   - A closed model (a fixed number of virtual users looping, as with k6
     `constant-vus` or `ramping-vus`) fits concurrency tests such as N
     simultaneous sessions or websocket clients. When used for rate goals it
     suffers from coordinated omission: slow responses delay the next request,
     the slow period is under-sampled, and tail latency looks better than users
     experience.
   - Locust users are a closed model. `constant_throughput` caps each user's
     rate but cannot hold it when responses slow down, so compare the achieved
     rate with the target.
4. **Size the generator with Little's law**, L = λW: requests in flight equal
   the arrival rate times the time each spends in the system. At 200 requests per
   second and 0.25 s per request, about 50 are in flight. Set k6
   `preAllocatedVUs` above that and `maxVUs` well above it. A nonzero
   `dropped_iterations` means the generator could not keep the schedule, so the
   test did not apply the intended rate.
5. **Write the script.**
   - Vary data per iteration so one hot key does not turn the test into a cache
     benchmark, and follow the real endpoint mix.
   - Use tokens for test-only accounts, passed through the environment.
   - Group URLs that contain IDs under one tag name so metrics stay bounded.
   - Use checks for correctness (status, body) and thresholds for latency. Never
     count a slow but correct response as an error.
6. **Set thresholds from the SLOs.** Latency percentiles on `http_req_duration`,
   error rate on `http_req_failed`, and the `checks` pass rate. Add an
   `abortOnFail` threshold as a safety stop when the target is clearly failing.
7. **Prepare.** Mock or sandbox third-party APIs, create isolated test data with
   a recognizable prefix or tenant, and open the resource dashboards.
8. **Run small, then ramp.** A smoke run at a very low rate validates the script.
   Then run the real profile while watching the target's resources and the
   generator's own CPU and network; a saturated generator invalidates the result.
   Stop a run with Ctrl-C in the terminal running it, which stops k6 gracefully,
   or let the `abortOnFail` threshold stop it. Do not restart shared services
   (databases, caches, queues) to recover; ask their owners first.
9. **Analyze.**
   - Use percentiles, never averages alone. Compare the achieved rate with the
     target, and check `dropped_iterations`.
   - Find the knee where latency climbs faster than rate, and the first
     saturated resource there (connection pool, CPU, GC, thread pool, queue).
   - Separate generator limits from system limits.
10. **Clean up.** Delete the test data you created, and stop the local
    containers and processes you started.

## Reference script (illustrative)

A k6 load test holding a target rate. The rate, duration, and thresholds are
examples; take them from the project's SLOs and traffic data.

```javascript
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.TARGET_URL;   // a non-production host; no default on purpose
const TOKEN = __ENV.LOADTEST_TOKEN;  // test-only account, never committed
if (!BASE_URL || !TOKEN) {
  throw new Error('Set TARGET_URL and LOADTEST_TOKEN');
}

export const options = {
  scenarios: {
    create_order: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 200),  // iterations started per timeUnit, whatever the latency
      timeUnit: '1s',
      duration: __ENV.DURATION || '10m',
      preAllocatedVUs: 100,  // L = λW: 200/s x 0.25 s = 50 in flight, plus headroom
      maxVUs: 400,
    },
  },
  thresholds: {
    // Correctness and latency are judged separately.
    http_req_failed: [
      'rate<0.001',
      { threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '30s' },  // safety stop
    ],
    checks: ['rate>0.999'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
  },
};

export default function () {
  // Prefix test data so cleanup can find it.
  const sku = `LOADTEST-${Math.floor(Math.random() * 500)}`;
  const res = http.post(`${BASE_URL}/api/v1/orders`, JSON.stringify({ sku, quantity: 1 }), {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
    tags: { name: 'POST /api/v1/orders' },  // one metric series, not one per URL
  });
  // Checks assert correctness only; slow responses are not counted as errors here.
  check(res, {
    'status is 201': (r) => r.status === 201,
    'returns an order id': (r) => r.status === 201 && Boolean(r.json('id')),
  });
}
```

Smoke run, then the real run, with the token exported in the environment rather
than typed on the command line (paths and hosts are examples):

```bash
k6 run -e TARGET_URL=https://perf.example.internal -e RATE=1 -e DURATION=30s tests/load/orders.js
k6 run -e TARGET_URL=https://perf.example.internal tests/load/orders.js
```

For a stress test, switch to `ramping-arrival-rate` with `startRate`, `stages`
of `{ target, duration }`, and a final stage above the expected peak. Treat its
thresholds as observations, since the point is to find where they break.

## Guardrails

- Never load-test production or a shared environment without written approval
  that names the environment, window, and peak rate.
- Mock or sandbox third-party APIs; real calls can bill, rate-limit, or notify
  real people.
- Never restart, scale, or reconfigure shared services to recover from a test
  without their owners' approval. Stop the generator instead.
- Use only test accounts and synthetic data; never production records or real
  credentials. Clean up all data the test created.
- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's work.
- Never loosen a threshold after a run to make it pass. If an SLO is wrong, say
  so in the report and leave the change to its owner.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately; never chain alternatives with `||`.

- The smoke run completes with all checks passing.
- The real run's exit code reflects its thresholds (k6 exits nonzero when a
  threshold fails), and the summary shows the achieved rate near the target with
  zero or explained `dropped_iterations`.
- The generator stayed below saturation for the whole run.
- Resource graphs for the target cover the run window, and the first saturated
  resource is named with evidence.
- Cleanup removed every record with the test prefix or tenant, confirmed by a
  query against the test environment.

## Report

- **Target and approval:** environment, window, who approved, and mocked
  dependencies.
- **Workload:** tool and version, test type, executor, rate or VU profile,
  duration, endpoint mix, and data variety.
- **Results:** achieved versus target rate, p50, p95, and p99 latency, error
  rate, check pass rate, and dropped iterations.
- **Verdict:** each threshold, pass or fail, with its SLO source.
- **Capacity:** the knee, the first saturated resource with evidence, and
  generator health.
- **Cleanup:** data removed and processes stopped.
- **Recommendations and not verified:** scaling or code changes worth testing,
  and checks that could not run.

## Optional delegation

The `performance-profiler` subagent can analyze results and profile the
bottleneck found at the knee, against the same non-production target. The
`resilience-reviewer` subagent can review how the system degraded. One agent can
complete this workflow alone.
