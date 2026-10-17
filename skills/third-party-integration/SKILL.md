---
name: third-party-integration
description: "Integrate an external HTTP API or webhook provider safely with a thin client that owns auth, timeouts, bounded retries with jittered backoff, idempotency keys, rate limits, and error mapping, plus webhook signature verification, replay protection, and deduplication. Use when adding or hardening a payment, messaging, CRM, or other vendor API integration or webhook endpoint. Not for designing your own API (use the api-design skill) or LLM provider calls (use the build-llm-feature skill)."
---

# Third-Party Integration

Connect the application to an external API or webhook provider so that slow,
failing, duplicated, or hostile traffic cannot corrupt data or take the
application down. The stance is **assume the network and the provider fail**:
every call has a deadline, every retry is safe to repeat, and every inbound
webhook is verified before it is trusted.

## When to use

- Adding a client for a vendor API (payments, email or SMS, CRM, shipping,
  identity, storage) or a webhook endpoint for one.
- An existing integration hangs, double-charges, drops events, hits rate limits,
  or logs secrets.
- Moving a provider from test mode to live mode.

## When not to use

- Designing the application's own public API: use the `api-design` skill.
- Building the application's own endpoints and handlers: use the `backend-api`
  skill; this skill covers the outbound client and inbound webhook edges.
- Calling an LLM provider: use the `build-llm-feature` skill.
- A dedicated security review of the integration: use the `security-review`
  skill.

## Inputs to gather

Discover these from the repository and the provider's documentation before
asking. Ask the user only about what remains ambiguous and would change the
result.

- The provider's documentation for the exact API version in use: authentication,
  rate limits, idempotency support, pagination, error format, retry guidance,
  webhook signature scheme, and delivery semantics. Pin the API version if the
  provider supports it.
- Existing HTTP client, retry, or circuit-breaker libraries, error model, logging
  and redaction helpers, secret manager, and job queue in the project.
- Which calls are on a user request path and which can be queued, and whether
  the feature can degrade when the provider is down.
- Sandbox or test-mode credentials, and the project's test and lint commands.

## Workflow

1. **Read the provider contract.** Record auth method and scopes, rate limits,
   which operations are idempotent or accept an idempotency key, pagination
   style, error codes and which are retryable, and webhook retry behavior.
   Prefer the provider's official SDK if it is maintained, but still wrap it.
   For version-exact lookups, delegate to the `docs-researcher` subagent.
2. **Build one thin client module** that owns base URL, auth, API version
   header, timeouts, retries, and error mapping. The rest of the application
   calls typed functions such as `createRefund(...)`, never raw HTTP.
3. **Set timeouts on every call:** a connect timeout and a total deadline. Size
   them from the project's latency budget; for example a 2 to 5 second total on
   a request path. In Node.js, `AbortSignal.timeout(ms)` bounds a `fetch`. In
   Python, `requests` and `httpx` timeouts apply per phase or per read, not to
   the whole call, so enforce a total deadline around the call (for example
   `asyncio.timeout` in async code) or use `aiohttp.ClientTimeout(total=...)`.
4. **Retry only what is safe to repeat:** idempotent methods (`GET`, `PUT`,
   `DELETE`) or requests carrying an idempotency key the provider honors.
   Generate the key once per logical operation, store it with the operation,
   and reuse it on every retry. Retry connection errors, `429`, and the `5xx`
   statuses the provider documents as transient; never retry `400`, `401`,
   `403`, or `422`.
   - Backoff with full jitter: wait a random time between 0 and
     min(cap, base times 2 to the power of attempt), for example base 200 ms and
     cap 10 s, with a small maximum attempt count inside the total deadline.
   - Honor `Retry-After` (seconds or an HTTP date). If it exceeds the remaining
     deadline, fail fast or move the work to a queue.
   - A timed-out, non-idempotent call has an unknown outcome. Do not retry it
     blindly; reconcile by looking up the operation by your own reference ID.
5. **Respect rate limits.** Throttle on the client side to the documented
   limits, shared across workers if several processes use one key. Track the
   provider's remaining-quota headers where offered (names vary by provider).
   Move bulk work to a queue.
6. **Contain an optional dependency.** Where the feature can work without the
   provider, add a circuit breaker (open after repeated failures, probe after a
   cool-down) using the project's resilience library, and a fallback: cached
   data, a degraded response, or a queued retry.
7. **Map errors** into the application's error model: transient (retryable),
   authentication or configuration (alert, do not retry), invalid request (a
   bug or bad input), not found, and conflict. Keep the provider's request ID
   and error code in logs; do not show raw provider messages to end users.
8. **Treat responses as untrusted input.** Validate the fields you use at the
   boundary, tolerate unknown fields and enum values, and follow pagination
   cursors with a page limit instead of computing offsets.
9. **Receive webhooks safely:**
   - Verify the signature over the **raw request body** before parsing it; JSON
     that was parsed and re-serialized will not match. Use the provider SDK's
     verifier when one exists. Raw body access: Django `request.body`, Flask
     `request.get_data()`, FastAPI `await request.body()`, Express
     `express.raw({ type: 'application/json' })` on that route.
   - Compare signatures in constant time and reject timestamps outside the
     provider's tolerance to block replay.
   - Persist or enqueue the verified event, return `2xx` quickly, and process it
     asynchronously; providers retry on slow or failed responses.
   - Deduplicate by event ID with a unique constraint, recorded in the same
     transaction as the event's effects. Delivery is at least once.
   - Tolerate out-of-order delivery: compare the object's version or timestamp,
     or re-fetch the current object from the API before acting.
   - Acknowledge and log unknown event types instead of failing them.
10. **Store credentials in the secret manager** with least-privilege scopes or
    restricted keys, separate keys per environment, and a rotation plan
    (webhook verification may need to accept two secrets during rotation).
11. **Test without the live provider:** sandbox or test mode, recorded fixtures
    with secrets and personal data scrubbed, and fault tests for timeouts,
    `429` with `Retry-After`, a `503` then success, malformed responses, bad
    signatures, stale timestamps, duplicate events, and out-of-order events. Use
    the `contract-testing` skill for consumer contract tests.
12. **Instrument it:** latency and error rate per operation, retry count,
    rate-limit headroom, circuit state, webhook processing lag, and signature
    failures. Use the `observability-setup` skill to follow project patterns.

## Worked example: webhook signature check (illustrative Python)

Many providers sign `timestamp + "." + raw_body` with HMAC-SHA256 and send
`t=...,v1=...` in a header. Follow your provider's exact scheme; this sketch
shows the required properties.

```python
from __future__ import annotations

import hashlib
import hmac
import time

TOLERANCE_SECONDS = 300  # use the provider's documented tolerance


class InvalidSignature(Exception):
    pass


def verify_webhook(raw_body: bytes, header: str, secret: bytes,
                   now: float | None = None) -> None:
    """Verify a header like 't=1700000000,v1=hexdigest' (illustrative scheme)."""
    timestamp, candidates = None, []
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        if key == "t" and value.isascii() and value.isdigit():
            timestamp = int(value)
        elif key == "v1":
            candidates.append(value)
    if timestamp is None or not candidates:
        raise InvalidSignature("malformed signature header")

    current = time.time() if now is None else now
    if abs(current - timestamp) > TOLERANCE_SECONDS:
        raise InvalidSignature("timestamp outside tolerance")

    signed = str(timestamp).encode() + b"." + raw_body
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest().encode()
    # Several v1 values can arrive during secret rotation; accept any match.
    if not any(hmac.compare_digest(expected, c.encode()) for c in candidates):
        raise InvalidSignature("signature mismatch")
```

The handler returns `400` on `InvalidSignature` without echoing details, then
deduplicates by event ID before enqueueing. The timestamp window limits replay;
deduplication catches replays inside the window.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before any call against live provider accounts, especially calls that move
  money, send messages, or change customer data, and before registering webhook
  URLs or changing provider dashboard settings. Use sandbox mode by default.
- Never log API keys, `Authorization` headers, webhook secrets, or full payloads
  containing personal data. Log the operation, status, latency, and provider
  request ID.
- Never disable TLS verification, and never add a flag that skips webhook
  signature checks outside tests.
- Never put provider credentials in source, fixtures, client-side bundles, or
  build arguments.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Unit and fault tests pass for timeouts, retry limits, `Retry-After`, error
  mapping, and the non-retry of unsafe requests.
- Webhook tests pass for a valid signature, a tampered body, a stale timestamp,
  a duplicate event ID, and an out-of-order event.
- A sandbox run of the main flow succeeds end to end, if sandbox credentials are
  available.
- Logs from the test run contain no secrets or unredacted personal data.
- Type check, lint, and the project's test suite pass.

## Report

- **Provider and version:** API version pinned, documentation pages relied on.
- **Client:** timeouts, retry policy, idempotency handling, rate limiting,
  circuit breaker or fallback, and error mapping.
- **Webhooks:** signature scheme, tolerance, deduplication store, ordering
  strategy, and async processing path.
- **Credentials:** where they live, scopes, and rotation notes.
- **Verification:** each command and its result, and sandbox evidence.
- **Not verified:** checks that could not run and why (for example no sandbox
  account), and any provider behavior assumed from documentation only.

## Optional delegation

The `docs-researcher` subagent can look up version-exact provider documentation
for auth, limits, and webhook schemes. The `resilience-reviewer` subagent can
review timeouts, retries, and fallbacks; the `security-reviewer` subagent can
review the webhook endpoint and credential handling. The `test-writer` subagent
can write the fault tests. The workflow above stays complete for a single agent.
