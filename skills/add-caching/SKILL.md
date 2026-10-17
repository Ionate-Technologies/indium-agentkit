---
name: add-caching
description: "Add or change caching (in-process memoization, Redis or Memcached, HTTP Cache-Control and ETag headers, CDN rules, ORM query caches) only after measuring that it helps, with keys that include every input such as user, tenant, locale, and permissions, invalidation on writes, stampede protection, and fail-open behavior. Use when a measured hot path needs a cache, or cached data is stale, leaks across users, or stampedes. Not for finding the bottleneck (use the performance-optimization skill) or a slow query (use the query-optimization skill)."
---

# Add Caching

Add a cache that makes a measured path faster without serving one user's data
to another or serving data staler than the product allows. The stance is
**measure first, correctness before hit rate**: a cache is a copy with a
staleness contract, and every key, header, and invalidation path is part of
that contract.

## When to use

- A profiled hot path repeats the same expensive read or computation, and a
  baseline is recorded.
- Adding or changing `Cache-Control`, `ETag`, `Vary`, or CDN caching rules.
- A cache serves stale data, another user's or tenant's data, or cached
  errors, or the source is overloaded when hot entries expire.

## When not to use

- The bottleneck is not yet known: use the `performance-optimization` skill to
  profile first.
- A slow query: use the `query-optimization` skill first. A cache in front of a
  fixable query still pays the full cost on every miss, and turns a cold or
  failed cache into an outage.
- LLM response or prompt caching: use the `build-llm-feature` skill. CI
  dependency and build caches: use the `ci-pipeline` skill.
- An independent security review of a caching change: delegate to the
  `security-reviewer` subagent.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The baseline: metric, workload, current latency, source load, and the profile
  or trace showing the repeated cost. If there is none, measure first.
- The freshness requirement per data type, from the product owner or spec: how
  stale it may be, and whether users must see their own writes immediately.
- Every input that changes the result: user, tenant, roles and permissions,
  locale, currency, time zone, API version, feature flags and experiment
  variants, device class, query parameters, and request headers.
- Existing cache infrastructure and clients, their timeouts and eviction
  settings, and whether a Redis instance is shared with queues or sessions.
- Every write path to the underlying data (handlers, admin tools, jobs,
  imports, other services), found by searching for the tables or models.
- The project's test command and benchmark or load-test tooling.

## Workflow

1. **Confirm a cache is the right fix.** From the baseline, estimate the hit
   ratio (how often a key repeats within its TTL) and the saving per hit. Rule
   out cheaper fixes first: a missing index, an N+1 pattern, a redundant call.
   Write down the expected gain so the result can be checked.
2. **Decide what is safe to cache.** Good candidates are read far more than
   written, tolerate the agreed staleness, and are identical for everyone who
   shares the key. Treat these as unsafe unless keyed and scoped precisely:
   per-user or per-tenant data, permission-filtered lists, prices and stock
   where staleness costs money, security decisions (authorization results,
   revoked sessions or tokens), and data under an erasure obligation, which
   must leave the cache when it leaves the database.
3. **Choose the layer.**
   - **In-process memoization** is fastest but per process, inconsistent across
     replicas, and lost on restart. Bound it (Python
     `functools.lru_cache(maxsize=...)`, a size- and TTL-bounded LRU in Node);
     an unbounded dict or `Map` is a memory leak, and `lru_cache` on a method
     keeps instances alive while they are cached.
   - **A shared cache** (Redis, Memcached) is consistent across replicas and
     needs client timeouts and a fallback.
   - **HTTP and CDN caching** is the cheapest per hit for public responses, the
     hardest to invalidate, and the easiest place to leak personal data.
   - **Framework and ORM caches** follow the same rules. For example Rails
     `Rails.cache.fetch` accepts `race_condition_ttl`; Django's `cache_page`
     keys by URL plus the response's `Vary` headers, so per-user pages must vary
     correctly or not be cached. Framework data-cache defaults change between
     major versions (Next.js among them); check your version.
4. **Design the key.** Include every input that changes the result plus a
   schema version prefix. Build each key in one function from a canonical form
   (sorted parameters, normalized case), and hash long or sensitive parts so
   keys do not expose emails or tokens in monitoring tools. When the result
   depends on permissions, key by the role or permission set that produced it,
   or do not share it. A missing tenant or user component is a cross-tenant
   data leak, the most serious caching bug.
5. **Set HTTP caching headers deliberately.**
   - Personal or sensitive responses: `Cache-Control: no-store`, or `private`
     when only the user's own browser may keep a copy. A shared cache does not
     reuse a response to a request with `Authorization` unless the response
     says `public`, `s-maxage`, or `must-revalidate`; adding them to an
     authenticated response opts it into shared caching.
   - Public responses: `max-age` for browsers, `s-maxage` for shared caches and
     CDNs, optionally `stale-while-revalidate` and `stale-if-error`.
   - `no-cache` means "store, but revalidate before every use"; it does not mean
     "do not store".
   - `Vary` lists the request headers that change the body (for example
     `Accept-Encoding`, `Accept-Language`). Many CDNs honor `Vary` only partly;
     set the CDN cache key explicitly and check its documentation.
   - Validators: an `ETag` (or `Last-Modified`) that changes whenever the
     representation changes, answered with `304 Not Modified` on a matching
     `If-None-Match` (or `If-Modified-Since`). Different encodings or locales
     need different ETags.
   - Never store a response carrying `Set-Cookie` in a shared cache. Cache at
     the CDN by explicit route rules backed by origin headers, not by file
     extension: extension rules can store a personal page requested with a
     static-looking suffix (web cache deception). A request header that changes
     the response but is not in the cache key (for example `X-Forwarded-Host`
     echoed into links) enables cache poisoning; key it or stop using it.
6. **Invalidate on every write path.** A TTL bounds staleness; it is not the
   invalidation plan.
   - **Delete on write:** delete the key after the database commit, never
     before; a concurrent reader can refill it with the old value before the
     commit lands.
   - **Versioned keys:** put a version in the key that each write bumps in its
     own transaction (a `version` or `updated_at` column), so old entries become
     unreachable and expire. This survives races and multi-key invalidation.
   - **Write-through:** write the new value after commit; concurrent writers
     can finish out of order, so pair it with versions or short TTLs.
   - **The read race:** a reader misses and loads the old row, a writer commits
     and deletes, then the reader stores the old value, stale until the TTL.
     Bound it with the TTL, use versioned keys, or use a short fill lock or
     lease. For CDNs, purge by URL or tag after the write (mechanisms vary by
     vendor) and keep TTLs short where purges are slow or unreliable.
7. **Prevent stampedes.** When a hot key expires, every request misses at once.
   Coalesce concurrent misses (single-flight per key in process, or a short
   distributed lock with a timeout), serve stale while one caller refreshes
   (`stale-while-revalidate`, or a soft expiry inside a longer hard TTL), add
   jitter to TTLs so entries written together do not expire together, and
   pre-warm critical keys after a deploy or flush.
8. **Cache absence, not failure.** Cache "not found" with a short TTL when
   repeated misses are costly, and clear it on create. Do not cache errors,
   timeouts, partial results, or results from a degraded dependency; where that
   is unavoidable, keep them for seconds, not the normal TTL.
9. **Bound memory and choose eviction.** Set a memory limit and policy (Redis
   `maxmemory` and `maxmemory-policy`; open-source Redis defaults to
   `noeviction`, so writes fail when it is full, and managed services differ).
   Keep caches off a Redis instance whose queues, sessions, or locks must never
   be evicted. Put a TTL on every key and cap value size.
10. **Keep serialization compatible across deploys.** During a rolling deploy,
    old and new versions read the same keys. Use a portable format such as JSON
    rather than language-native pickles, bump the key prefix when the cached
    shape changes, and never unpickle data from a cache that other systems can
    write to.
11. **Make the cache optional.** Give the client short connect and read
    timeouts (use the project's latency budget; for example tens of
    milliseconds), treat cache errors as misses, and count them. Failing open
    sends every request to the source, so confirm the source can carry the full
    miss load, or protect it with coalescing, a concurrency limit, or serving
    stale.
12. **Measure the result** against the baseline: hit ratio, p50 and p95
    latency, source load, memory, and evictions. Remove a cache that does not
    meet its expected gain.

## Worked example: read-through cache (illustrative Python)

Prices here depend on tenant, role, locale, and currency, so the key carries
all four plus a catalog version that each catalog write bumps in its own
transaction; writes invalidate by changing the key. The caller reads
`catalog_version` from the database, a cheap indexed read.

```python
# Illustrative. `cache` is any client with get(key) and set(key, value,
# ex=seconds), such as redis-py with short socket_connect_timeout and
# socket_timeout values.
from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

KEY_SCHEMA = "v3"  # bump when the cached value's shape changes
TTL_SECONDS = 300  # use the product's freshness requirement
NEGATIVE_TTL_SECONDS = 30
_STRIPES = [threading.Lock() for _ in range(64)]  # bounded, unlike a lock per key


def price_list_key(tenant_id: str, role: str, locale: str, currency: str,
                   catalog_version: int) -> str:
    parts = json.dumps([tenant_id, role, locale, currency], separators=(",", ":"))
    digest = hashlib.sha256(parts.encode()).hexdigest()[:32]
    return f"{KEY_SCHEMA}:price-list:{digest}:cv{catalog_version}"


def _get(cache, key: str) -> Any:
    try:
        return cache.get(key)
    except Exception:  # down or slow: treat as a miss and read the source
        log.warning("cache get failed; reading from source", exc_info=True)
        return None


def _set(cache, key: str, value: str, ttl: int) -> None:
    try:
        cache.set(key, value, ex=ttl)
    except Exception:
        log.warning("cache set failed", exc_info=True)


def get_or_load(cache, key: str, load: Callable[[], Any]) -> Any:
    raw = _get(cache, key)
    if raw is not None:
        return json.loads(raw)  # "null" is a cached miss and returns None
    with _STRIPES[hash(key) % len(_STRIPES)]:  # coalesce misses in this process
        raw = _get(cache, key)  # another thread may have filled it meanwhile
        if raw is not None:
            return json.loads(raw)
        value = load()  # exceptions propagate and are never cached
        ttl = NEGATIVE_TTL_SECONDS if value is None else TTL_SECONDS
        _set(cache, key, json.dumps(value), int(ttl * random.uniform(0.9, 1.1)))
        return value
```

Coalescing here is per process, and keys that share a stripe wait for each
other; use the project's single-flight helper or a distributed lock if many
replicas miss together. `load` must have its own timeout, because waiting
threads queue behind it. Rate-limit the warning logs in production.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before flushing or purging a shared or production cache or CDN, changing
  eviction or memory settings on a shared instance, or changing CDN rules.
  Flushes can stampede the source.
- Never cache personal, per-tenant, or permission-dependent data under a key
  that lacks the inputs that scope it, and never mark such responses `public`
  or give them `s-maxage`.
- Never cache authorization decisions longer than the product accepts for a
  revoked permission to keep working.
- Do not add a cache to hide a slow query or a bug; fix or route those first.
- Never put secrets or raw personal data in cache keys or log lines.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- **Per user and tenant:** user A then user B (and tenant A then tenant B, and
  two locales or roles) make the same request; each gets only their own data,
  with the cache warm.
- **Invalidation:** read, write through every write path, read again; the new
  value appears within the agreed staleness (immediately for read-your-writes).
- **Cache unavailable:** with the client failing or timing out, responses stay
  correct and latency stays within the timeout budget.
- **HTTP headers:** personal responses carry `no-store` or `private`; public
  ones carry the intended `max-age`, `s-maxage`, and `Vary`; a matching
  `If-None-Match` returns `304`.
- **Stampede and errors:** many concurrent misses on one key call the loader
  once per process; a loader error is not cached.
- **Deploy compatibility:** a value written under the previous key schema is
  ignored or read correctly, never misparsed.
- **Gain:** hit ratio, latency, and source load against the baseline, measured
  as in the `performance-optimization` skill.
- Lint, type check, and the project's test suite pass.

## Report

- **Baseline and result:** metric, workload, before and after numbers, and hit
  ratio.
- **What is cached:** layer, data, key structure with every input, TTL, and
  staleness contract.
- **Invalidation:** each write path and how it invalidates, and the race bound.
- **HTTP and CDN:** headers and CDN rules per route, if any.
- **Failure behavior:** timeouts, fail-open path, stampede protection, memory
  limit, and eviction policy.
- **Verification:** each test and command with its result.
- **Not verified:** checks that could not run and why (for example no CDN in a
  test environment).

## Optional delegation

The `performance-profiler` subagent can record the baseline and the after
measurement. The `security-reviewer` subagent can check keys, headers, and CDN
rules for cross-user leaks and cache poisoning, and the `resilience-reviewer`
subagent can review the fail-open path. The workflow above stays complete for a
single agent.
