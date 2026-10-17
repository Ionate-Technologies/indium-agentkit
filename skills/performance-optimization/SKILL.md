---
name: performance-optimization
description: "Speed up a specific slow path (latency, throughput, CPU, memory, or startup) by measuring a reproducible baseline, profiling to find the bottleneck, making the smallest change, and proving the gain against a separate baseline build with a statistical comparison. Use when something is measurably slow or has regressed and the cause is not yet proven. Not for slow database queries (use the query-optimization skill) or capacity testing under traffic (use the load-testing-suite skill)."
---

# Performance Optimization

Make a measured performance characteristic better, and prove it. The stance is
**profile first, change second, re-measure third**: no change without a
bottleneck shown by profiling data, and no claim without a statistical
comparison of two distinct builds under the same workload.

## When to use

- An endpoint, job, function, page, CLI command, or startup is measurably slow,
  or a benchmark regressed.
- A proposed optimization needs evidence before it merges.

## When not to use

- A slow query, missing index, N+1 pattern, or plan regression: use the
  `query-optimization` skill.
- System capacity or behavior under traffic: use the `load-testing-suite` skill.
- Wrong behavior rather than slow behavior: use the `systematic-debugging` skill.
- Adding a cache once the bottleneck is proven: use the `add-caching` skill.
- Memory that grows without bound in a long-running process: use the
  `memory-leak-investigation` skill.

## Inputs to gather

Discover these from the repository and the report before asking. Ask only about
what remains ambiguous and would change the result.

- The metric and the target: p50 or p95 latency, throughput, CPU time, peak
  memory, or cold start, from the complaint, an SLO, or the regression. If the
  metric is ambiguous, ask before measuring.
- A concrete workload: the request, input size, or dataset, or the nearest
  existing benchmark. Never optimize against an undefined workload.
- The environment: machine, OS, CPU count, runtime version, and build mode
  (release, not debug).
- Existing benchmark and profiling tooling (bench scripts, `pytest-benchmark`,
  `go test -bench`, criterion, JMH, k6) and the project's test commands.

## Workflow

1. **Define the run contract.** Write down the metric, workload, environment,
   target, and noise controls. Confirm the target is local or a designated
   non-production environment.
2. **Baseline.** Build in release mode, warm up, and take repeated runs (as a
   guideline at least 10 runs of many samples each; more when noisy). Record
   commands, versions, seeds, and inputs. Quiet the machine: close background
   load, stay on mains power, and note what you could not control.
3. **Check the method's noise (A/A).** Run the comparison with the baseline
   build on both sides (two instances on two ports). If the interval for the
   difference excludes zero, the method is too noisy to judge a change; fix it
   first.
4. **Profile under the same workload.** Use the project's tools or a standard
   profiler, writing output to a scratch directory:
   - Python: `py-spy record -o <scratch>/profile.svg --duration 30 -- python -m app.server`
     (attaching with `--pid` may need elevated permissions; ask first).
   - Node: `node --cpu-prof --cpu-prof-dir <scratch> server.js`, then open the
     `.cpuprofile` in browser DevTools or speedscope.
   - Go: `go test -bench . -cpuprofile <scratch>/cpu.out`, then
     `go tool pprof -top <scratch>/cpu.out`.
   - Native code on Linux: `perf record -g`, then render a flamegraph. JVM:
     async-profiler. Browser: the DevTools Performance panel.
   - Memory problems need a heap or allocation profiler; waiting (I/O, locks)
     needs an off-CPU profile or tracing, not a CPU profile.
5. **Hypothesize.** Name the mechanism, the expected improvement as a range, and
   the side effects (memory, tail latency, readability, correctness risk).
6. **Make the smallest change** that addresses the measured bottleneck, one
   change at a time. No speculative optimizations, drive-by refactors, or
   dependency upgrades in the same change; ask before any dependency change.
7. **Compare two distinct builds.** The baseline is the commit before your
   change, built in its own worktree; the candidate is your working tree. Run
   them on separate ports and give the harness one URL per variant. Interleave
   runs, alternating which goes first, so drift does not favor either side, and
   confirm each port serves the build you think it does.
8. **Decide statistically.** Compare per-run statistics (each run's median or
   p95), not pooled samples, because samples within a run share warm-up and
   machine state. Report the difference with a bootstrap 95% confidence
   interval, or a Mann-Whitney U test if a statistics library is available.
   Claim an improvement only when the whole interval is on the improving side
   and the gain meets the target (use the project's threshold; for example 5%).
9. **Check behavioral equivalence.** Run the full test suite. If the optimized
   path lacks coverage, add a test that compares outputs on representative
   inputs before and after. An optimization that breaks behavior is reverted.
10. **Check secondary metrics** (memory, tail latency, throughput, startup) for
    regressions, then report.

## Reference harness (illustrative)

Two builds side by side, then an interleaved comparison. Keep the harness,
profiles, and results in a scratch directory outside the project, not in the
project's `scripts/`; add a benchmark to the repository only if the user asks,
following its conventions.

```bash
# Baseline: the commit before your change (HEAD while the change is uncommitted).
git worktree add --detach "<scratch>/perf-baseline" HEAD
# Build each tree in release mode with the project's commands, then start the
# baseline on port 8081 (from the worktree) and the candidate on port 8082.
python "<scratch>/bench_ab.py" --baseline http://127.0.0.1:8081/v1/search --candidate http://127.0.0.1:8082/v1/search
# Afterward, stop both servers and remove only the worktree you created.
git worktree remove "<scratch>/perf-baseline"
```

```python
"""Interleaved A/B latency benchmark against two running builds (illustrative).

Keep this file and its output in a scratch directory outside the project:
  python bench_ab.py --baseline http://127.0.0.1:8081/v1/search \
      --candidate http://127.0.0.1:8082/v1/search --rounds 12
"""
import argparse
import json
import random
import statistics
import time
import urllib.request
from pathlib import Path

BODY = json.dumps({"query": "red sneakers", "limit": 20}).encode()  # synthetic


def time_request(url: str) -> float:
    req = urllib.request.Request(url, data=BODY, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()
    return (time.perf_counter() - start) * 1000.0  # milliseconds


def run_median(url: str, requests: int, warmup: int) -> float:
    for _ in range(warmup):
        time_request(url)
    return statistics.median(time_request(url) for _ in range(requests))


def bootstrap_ci(base: list, cand: list, iters: int = 10000, seed: int = 1) -> tuple:
    """95% percentile-bootstrap interval for median(cand) - median(base)."""
    rng = random.Random(seed)
    diffs = sorted(
        statistics.median(rng.choices(cand, k=len(cand)))
        - statistics.median(rng.choices(base, k=len(base)))
        for _ in range(iters)
    )
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters) - 1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, help="URL served by the baseline build")
    parser.add_argument("--candidate", required=True, help="URL served by the candidate build")
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    args = parser.parse_args()
    if args.baseline == args.candidate:
        parser.error("baseline and candidate must be different builds on different URLs")

    base, cand = [], []
    for i in range(args.rounds):
        pairs = [(base, args.baseline), (cand, args.candidate)]
        if i % 2:
            pairs.reverse()  # alternate order so drift does not favor one side
        for results, url in pairs:
            results.append(run_median(url, args.requests, args.warmup))

    lo, hi = bootstrap_ci(base, cand)
    print(f"baseline median of run medians:  {statistics.median(base):.2f} ms")
    print(f"candidate median of run medians: {statistics.median(cand):.2f} ms")
    print(f"candidate - baseline 95% CI: [{lo:+.2f}, {hi:+.2f}] ms")
    try:
        from scipy.stats import mannwhitneyu  # optional; never install it for this
        print(f"Mann-Whitney U p = {mannwhitneyu(base, cand, alternative='two-sided').pvalue:.4f}")
    except ImportError:
        pass
    out = Path(__file__).with_name("bench_results.json")
    out.write_text(json.dumps({"baseline_ms": base, "candidate_ms": cand, "ci_ms": [lo, hi]}, indent=2))


if __name__ == "__main__":
    main()
```

For non-HTTP targets, use the ecosystem's comparator when available:
`hyperfine` for two CLI builds, `benchstat` for Go benchmark output, criterion's
saved baselines for Rust, and `pyperf compare_to` for Python microbenchmarks.

## Reading a flamegraph (worked example)

1. Width is the share of sampled time; color carries no meaning. As a guideline,
   frames under about 2% of total width are not worth optimizing.
2. Find wide frames with high self time (little width in their children). In the
   example, `rank_results` covers 61% of the width, and 48 of those points are
   self time in a nested `score_document` loop that compiles a regular
   expression per document.
3. Follow the stack up to confirm it belongs to the reported path
   (`handle_search` calls `rank_results`), not a background worker.
4. Hypothesis: compiling the pattern once removes the per-document cost.
   Expected effect: a 35 to 50% lower median; side effect: one cached pattern.
5. If the wide frames are waits (`recv`, `epoll_wait`, lock acquisition), the
   problem is off-CPU: switch to tracing or an off-CPU profile instead of
   optimizing CPU work.

## Guardrails

- Profile before changing; change only what the profile implicates.
- Measure only local or designated non-production targets. Never put load on
  production without written approval.
- Keep benchmark scripts, profiles, and results in a scratch directory, not in
  the project tree.
- Use synthetic or anonymized payloads; never copy production records, tokens,
  or credentials into benchmarks, profiles, or reports.
- Never disable TLS verification, auth, rate limits, validation, or tests to win
  time. Added caching changes behavior (staleness, invalidation, memory); call
  it out and get agreement.
- If a change does not help, revert only your own change and record the
  rejected hypothesis. Never discard someone else's work. Remove only the
  worktrees you created.
- Never weaken a test or benchmark threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately; never chain alternatives with `||`.

- The A/A comparison's interval includes zero.
- The A/B comparison's interval lies entirely on the improving side, and the
  gain meets the target, with the same workload, environment, and build mode on
  both sides.
- Secondary metrics show no regression beyond the project's tolerance.
- Type check, lint, and the full test suite pass.

## Report

- **Contract:** metric, workload, environment, target.
- **Baseline:** commands, parameters, runs, and results.
- **Bottleneck:** profiler, the implicated frames with their share, and the call
  path.
- **Change:** hypothesis, files touched, and why it addresses the bottleneck.
- **Comparison:** baseline and candidate medians, the difference with its
  interval or p-value, the number of runs, and the A/A result.
- **Side effects:** secondary metrics, memory, and readability cost.
- **Tests:** each command and its result.
- **Remaining opportunities and not verified:** ranked next bottlenecks, and
  checks that could not run.

## Optional delegation

The `performance-profiler` subagent can take the baseline, profile, and
comparison measurements while you work on the change; re-run its key
comparison before acting on it. For database bottlenecks found while profiling,
use the `query-optimization` skill. One agent can complete this workflow alone.
