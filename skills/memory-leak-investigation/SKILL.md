---
name: memory-leak-investigation
description: "Find and fix memory leaks and unbounded growth in long-running Node.js, Python, JVM, or Go processes: confirm a real leak, reproduce it with a repeatable load loop, compare heap snapshots or profiles to find the retainer, fix or bound it, and prove the fix with a growth test. Use when memory climbs until OOM kills or restarts, heap after GC rises under steady load, or goroutines or tasks pile up. Not for slow code without growth (use the performance-optimization skill)."
---

# Memory Leak Investigation

Find the reference that keeps memory alive, release or bound it, and prove
memory stays flat under repeated work. The stance is **retainer before fix**: no
change until a comparison of snapshots or profiles names the object that grows
and the reference that holds it.

## When to use

- Memory (RSS or heap) climbs under steady load, and processes are OOM-killed,
  restarted at a memory limit, or slowed by garbage-collection pressure.
- Heap after garbage collection rises over hours, or one job, endpoint, or
  consumer is suspected of leaking.
- Goroutine, thread, task, file-descriptor, or connection counts keep growing.

## When not to use

- Slow but not growing: use the `performance-optimization` skill, and delegate
  measurement to the `performance-profiler` subagent.
- Wrong behavior unrelated to memory: use the `systematic-debugging` skill.
- Production is failing now (OOM kills on every replica): use the
  `incident-triage` skill to mitigate first, then return here.
- Designing a cache: use the `add-caching` skill. Sizing a local model: use the
  `local-llm-integration` skill. Firmware memory budgets: use the
  `rtos-firmware-development` skill.
- Reviewing a diff for goroutine or task leaks and other concurrency defects:
  delegate to the `concurrency-reviewer` subagent.

## Inputs to gather

Discover these from the repository and monitoring before asking. Ask only about
what remains ambiguous and would change the result.

- Runtime and version: `package.json` (`engines`), `.nvmrc`, `pyproject.toml`,
  `pom.xml`, `build.gradle`, `go.mod`, or the Dockerfile base image. In a
  polyglot repository, identify which process grows.
- Memory over time: RSS, heap after GC, GC activity, OOM-kill and restart
  events, and when growth began (a deploy, a traffic change, a new dependency).
- Limits: container memory limit, Node `--max-old-space-size`, JVM `-Xmx` or
  `-XX:MaxRAMPercentage`, Go `GOMEMLIMIT`.
- The workload that tracks the growth (endpoint, job, message type, tenant), and
  whether growth follows request count, distinct keys, or wall-clock time.
- The project's run and test commands, load scripts, and installed profilers.

## Workflow

1. **Confirm it is a leak.** Many runtimes let the heap grow toward its limit
   before collecting hard, so a high reading proves nothing. Compare the floor
   of the memory sawtooth (memory right after each GC) across steady load:

   | Pattern | Likely meaning |
   | --- | --- |
   | Floor rises with every unit of work and never returns | Leak: per-request objects are retained |
   | Rises, then plateaus | High but stable working set (warm caches, pools, JIT); size the limit instead |
   | Grows with distinct keys, flat when keys repeat | A cache or map without bounds |
   | RSS grows while the language heap after GC is flat | Native or off-heap memory (buffers, extensions, thread stacks) or fragmentation |
   | Grows with time even when idle | Timers, intervals, or background tasks accumulating |

   If memory is stable, report that with the evidence and stop. For suspected
   fragmentation, try allocator settings your platform documents (for example
   limiting glibc arenas with `MALLOC_ARENA_MAX`, or jemalloc) as an experiment
   and report the measured result.
2. **Reproduce off production.** Write a repeatable load loop against a local or
   non-production instance that drives the suspected operation N times, once
   with repeated inputs and once with unique ones. Warm up first (imports, JIT,
   pools, and bounded caches fill), force a GC where the runtime allows it
   (`node --expose-gc` with `global.gc()`, `gc.collect()`, `runtime.GC()`,
   `jcmd <pid> GC.run`), and sample memory every K iterations. Record the
   command, inputs, and growth per iteration. If it does not reproduce, narrow
   the workload from production signals before proposing a production capture.
3. **Capture evidence.** Take three snapshots at the same point in the loop:
   after warm-up, after N iterations, and after 2N. Objects that grow in both
   intervals are suspects; growth in the first interval only is warm-up. Write
   every dump and profile to a scratch directory outside the repository.
   - **Node.js:** run with `node --inspect` (it binds to 127.0.0.1:9229 by
     default; keep it on loopback, because the inspector can run arbitrary
     code) and take snapshots in Chrome DevTools (`chrome://inspect`, Memory
     panel), or call `v8.writeHeapSnapshot()` from a test or guarded hook. It
     blocks the event loop while writing and, per the Node documentation, needs
     about twice the heap size in memory. In DevTools, use the Comparison view
     (`# Delta`, `Size Delta`) or the Summary filter for objects allocated
     between two snapshots, then follow a growing constructor's Retainers panel
     to a root. Snapshots cover only the JavaScript heap: if
     `process.memoryUsage()` shows `external`, `arrayBuffers`, or RSS growing
     instead, suspect Buffers or native addons.
   - **Python:** `tracemalloc` (example below) tracks only allocations made
     through Python's allocators; memory a C extension allocates directly is
     invisible. When RSS grows faster than `tracemalloc.get_traced_memory()`,
     use `memray` with native tracking if available (Linux and macOS; check
     `memray run --help`). `objgraph.show_growth()` lists object types whose
     counts grow, and `objgraph.show_backrefs()` draws what refers to an object
     (rendering needs Graphviz). `tracemalloc` adds overhead; use it in the
     reproduction.
   - **JVM:** `jcmd <pid> GC.heap_dump <scratch>/heap.hprof` dumps live objects
     by default, which forces a full GC (check `jcmd <pid> help GC.heap_dump`).
     In Eclipse MAT or a similar analyzer, use the Leak Suspects report, the
     dominator tree by retained heap, and the path to GC roots excluding weak
     and soft references. For a lighter check, diff two
     `jcmd <pid> GC.class_histogram` outputs taken N iterations apart. In GC
     logs (JDK 9 and later: `-Xlog:gc*:file=<path>`; JDK 8:
     `-XX:+PrintGCDetails -Xloggc:<path>`), check whether old-generation
     occupancy after full collections rises. Off-heap growth (metaspace from
     class-loader leaks, direct buffers, thread stacks) needs Native Memory
     Tracking: start with `-XX:NativeMemoryTracking=summary`, then run
     `jcmd <pid> VM.native_memory summary`.
   - **Go:** serve `net/http/pprof` on a loopback or internal admin port, never
     the public listener. Fetch
     `curl -o <scratch>/heap1.pb.gz 'http://127.0.0.1:6060/debug/pprof/heap?gc=1'`
     at two points, then run
     `go tool pprof -top -sample_index=inuse_space -diff_base <scratch>/heap1.pb.gz <scratch>/heap2.pb.gz`.
     `inuse_space` is memory still held as of the last GC, where leaks show;
     `alloc_space` counts everything allocated since start, which shows churn,
     not leaks. For goroutine leaks, track `runtime.NumGoroutine()` and compare
     `/debug/pprof/goroutine?debug=1` over time: it groups goroutines by stack,
     and a stack whose count keeps rising (often blocked in a channel send,
     receive, or `select`) is the leak.
4. **Find the retainer.** Follow the retainer path from the growing objects to
   a root, and name both the code that adds the reference and the code that
   should release it. Common causes:
   - Event listeners, observers, or subscriptions added per request or
     connection and never removed (Node's `MaxListenersExceededWarning` hints).
   - Global maps, arrays, and caches without size or time bounds, keyed by
     request, user, or session. Python's `functools.cache` and
     `lru_cache(maxsize=None)` are unbounded, and a cache on an instance method
     keeps every `self` alive. Metrics labels with unbounded values (user IDs,
     raw URLs) add a series per value.
   - Closures that capture a large object (request, buffer, parsed document)
     and are stored in a long-lived registry or callback list.
   - Timers and intervals never cleared (`setInterval`, scheduled executors, Go
     tickers never stopped; timer collection changed in Go 1.23, so check the
     project's version).
   - Unclosed resources and streams: files, sockets, cursors, HTTP response
     bodies (Go `resp.Body.Close()`), and streams never consumed or destroyed.
   - Goroutines or tasks blocked forever: a send nobody receives after a
     timeout, a missing `ctx.Done()` case, or an await on an event never set.
   - Thread-local values on pooled threads, which live as long as the pool (Java
     `ThreadLocal` on executor threads, Python `threading.local` in pools).
   - ORM identity maps or persistence contexts held across a long batch, for
     example one Hibernate session or JPA `EntityManager` for a whole job.
   - Unbounded in-memory queues where producers outpace consumers, and small
     slices or substrings that keep a large backing array alive.
5. **Fix the retainer** with the smallest change that releases or bounds it:
   remove listeners in the matching teardown, give caches a maximum size and
   eviction (prefer a bounded cache the project already uses), clear intervals
   and stop tickers, close resources with the scoped construct (`with`,
   try-with-resources, `defer`, `finally`), cancel goroutines and tasks through
   a context or structured concurrency, scope ORM sessions per unit of work,
   and bound queues with backpressure. Weak references (`WeakMap`, `WeakRef`,
   `weakref`, `WeakHashMap`) fit only when an entry should vanish with its key.
   Raising a memory limit or scheduling restarts is a mitigation, not a fix:
   report it separately and ask before changing production.
6. **Prove it with a growth test.** Run the loop N times after a warm-up and
   assert memory stays within a bound. Prefer deterministic counters when they
   exist (cache size, `emitter.listenerCount(name)`, `runtime.NumGoroutine()`,
   open file descriptors); otherwise measure after a forced GC
   (`tracemalloc.get_traced_memory()`, `process.memoryUsage().heapUsed` under
   `node --expose-gc`, or `HeapAlloc` from `runtime.ReadMemStats` after
   `runtime.GC()`). Choose N and the bound so the leak exceeds the bound by a
   wide margin and noise does not. Confirm the test fails on the unfixed code
   and passes on the fix, then rerun the reproduction loop and compare curves.

## Worked example: tracemalloc comparison and growth test (illustrative)

```python
# Illustrative: run against the reproduction loop, never production.
import gc
import itertools
import tracemalloc
from collections import OrderedDict

_ids = itertools.count()
LEAKY = {}               # bug: one entry per request, never evicted
BOUNDED = OrderedDict()  # fix: keep only the newest MAX_ENTRIES entries
MAX_ENTRIES = 1_000


def handle_leaky(request_id):
    LEAKY[request_id] = bytearray(512)


def handle_fixed(request_id):
    BOUNDED[request_id] = bytearray(512)
    if len(BOUNDED) > MAX_ENTRIES:
        BOUNDED.popitem(last=False)  # evict the oldest entry


def run(handler, n):
    for _ in range(n):
        handler(next(_ids))


def snapshot():
    gc.collect()
    return tracemalloc.take_snapshot().filter_traces(
        [tracemalloc.Filter(False, tracemalloc.__file__)]
    )


def show_growth(handler, n=10_000):
    """Lines that grow in both intervals are suspects; warm-up grows once."""
    tracemalloc.start(25)  # keep 25 frames for "traceback" grouping
    run(handler, n)        # warm-up: imports, pools, and bounded caches fill
    snaps = [snapshot()]
    for _ in range(2):
        run(handler, n)
        snaps.append(snapshot())
    tracemalloc.stop()
    for old, new in zip(snaps, snaps[1:]):
        for stat in new.compare_to(old, "lineno")[:3]:
            print(stat)
        print("--")


def retained_bytes(handler, warmup=2_000, n=20_000):
    tracemalloc.start()
    try:
        run(handler, warmup)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        run(handler, n)
        gc.collect()
        return tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()


def test_fixed_handler_memory_is_bounded():
    # Use the project's budget; 20,000 leaked entries would hold over 10 MB.
    growth = retained_bytes(handle_fixed)
    assert growth < 256 * 1024, f"retained {growth} bytes over 20,000 calls"


if __name__ == "__main__":
    show_growth(handle_leaky)
    print("leaky:", retained_bytes(handle_leaky))
    print("fixed:", retained_bytes(handle_fixed))
```

`show_growth` puts the `LEAKY[request_id] = ...` line at the top of both
intervals with a similar positive delta each time: steady per-request
retention. `retained_bytes` reports megabytes for the leaky handler and close to
zero for the bounded one. Group by `"traceback"` instead of `"lineno"` when the
growing line is a shared helper and you need its callers.

## Guardrails

- Investigate in local or non-production environments. A heap dump, snapshot,
  or profile of a production process needs explicit approval: JVM heap dumps
  and Node snapshots pause the process while written, can need memory
  comparable to the heap (risking an OOM kill), and can fill the disk.
- Heap dumps, snapshots, and core files may contain secrets, tokens, and
  personal data. Handle them as sensitive: keep them outside the repository in
  a restricted location, never commit them, never upload them to third-party
  services or online analyzers without approval, and delete the ones you
  created when done.
- Never expose `--inspect`, a JMX port, or a pprof endpoint on a public
  interface; keep them on loopback or behind the project's admin access.
- Ask before adding profiling dependencies (for example objgraph, memray, or
  goleak), changing runtime flags in shared configuration, or restarting shared
  services.
- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never weaken a test, loosen a growth bound, or raise a memory limit to make a
  check pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The growth test fails on the unfixed code for the leak's reason and passes on
  the fix.
- The reproduction loop shows a flat post-GC floor over the same iterations and
  inputs that grew before; report both slopes.
- A snapshot or profile comparison after the fix no longer shows the retainer.
- Type check, lint, and the full test suite pass.
- After a normal release, post-GC memory stays flat for longer than the old
  time to OOM. If you cannot observe production, say so.

## Report

- **Symptom:** metric, growth rate, time to OOM or restart, and when it began.
- **Classification:** leak, stable working set, unbounded cache, native memory,
  or fragmentation, with the evidence.
- **Reproduction:** loop command, inputs, iterations, warm-up, and growth per
  iteration before and after the fix.
- **Evidence:** tool, snapshots or profiles compared, top growing types or
  allocation sites, and the retainer path.
- **Root cause:** `path:line` of the retaining reference and the missing
  release or bound.
- **Fix and growth test:** the change, the test and its bound, with failing and
  passing output.
- **Dumps:** each dump or profile created, where it is stored, and whether it
  was deleted.
- **Not verified:** runtimes, environments, or production behavior not observed.

## Optional delegation

The `performance-profiler` subagent can run the reproduction loop and capture
snapshots or profiles in a non-production environment while you read code. The
`debugger` subagent can test competing hypotheses about the retainer; re-run its
key comparison before acting on it. The `systematic-debugging` skill covers the
general hypothesis method. One agent can complete this workflow alone.
