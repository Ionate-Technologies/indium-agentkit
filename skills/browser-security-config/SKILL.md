---
name: browser-security-config
description: "Configure CORS, Content-Security-Policy, security headers (HSTS, nosniff, Referrer-Policy, Permissions-Policy, COOP), cookie attributes, and framing rules from the origins and embeds the app actually uses, rolling CSP out in report-only mode first and asserting headers in tests. Use when adding or fixing CORS, CSP violations, clickjacking, missing-header scanner findings, cookie flags, or third-party scripts and embeds. Not for login and session design (use the implement-authentication skill) or a full security review (use the security-review skill)."
---

# Browser Security Configuration

Set the response headers that tell browsers what the app may load, who may
embed it, and which other origins may read its responses. The stance is
**inventory, allowlist, then enforce**: every origin in a policy is one the app
is shown to need, CSP reports before it blocks, and a violation is fixed in the
code rather than silenced in the policy.

## When to use

- Adding or changing CORS for an API called from another origin, or debugging
  CORS errors.
- Adding, tightening, or enforcing a Content-Security-Policy, or triaging
  violation reports.
- A scanner, penetration test, or review flags missing headers, clickjacking,
  or weak cookie attributes.
- Adding third-party scripts, iframes, embeds, or popups (payments, analytics,
  chat, SSO).

## When not to use

- Session design, the session cookie, and CSRF tokens: use the
  `implement-authentication` skill. This skill audits every other cookie and
  the header layer.
- A broader security review of a change: use the `security-review` skill.
- Building the UI feature itself: use the `frontend-ship` skill, then apply
  this skill to the headers it needs.
- Serving user-uploaded files: use the `handle-file-uploads` skill.
- Cache headers for performance: use the `add-caching` skill.

## Inputs to gather

Discover these from the repository and a running local or staging instance.
Ask only about what remains ambiguous and would change the policy.

- **Where headers are set:** application middleware (for example Helmet for
  Express, Django `SecurityMiddleware` with django-csp, the Rails
  `content_security_policy` configuration, Spring Security headers, ASP.NET
  Core middleware, Next.js `headers()` or middleware), the reverse proxy (for
  example nginx or Caddy), the CDN or edge, and the hosting platform. Several
  layers often set the same header.
- **Response types:** HTML documents, API responses, static assets, downloads,
  error pages, and redirects.
- **Origins in use:** the app's domains and subdomains per environment, API
  callers, third-party scripts, styles, fonts, images, frames, websocket
  endpoints, and the identity provider. Ask about planned embeds that are not
  in the code yet.
- **HTTPS coverage:** whether every subdomain serves HTTPS, which decides HSTS
  `includeSubDomains`.
- **Reporting:** where CSP reports can be received and stored.
- **Commands:** test, lint, and end-to-end commands from `AGENTS.md`,
  `CLAUDE.md`, package scripts, or the `Makefile`.

## Workflow

1. **Capture current headers per response type** from local or staging, for
   example `curl -sS -D - -o /dev/null https://staging.example.com/` for a
   page, an API route, a static file, a 404, and a redirect. For each header,
   find the layer that sets it and choose one owner layer. Duplicates cause
   real failures: two CSP headers are both enforced, and a repeated
   `Access-Control-Allow-Origin` makes the browser reject the response.
2. **Inventory what the app needs.** Walk the main journeys with the browser's
   network panel open and list third-party origins by type (script, style,
   font, image, connect, frame). Search code and templates for inline
   `<script>` blocks, inline event handlers (`onclick=`), `javascript:` URLs,
   `eval` or `new Function`, inline styles, and `postMessage` or
   `window.opener` use. Each item is either allowed explicitly or refactored.
3. **Configure CORS only where another origin must read responses.**
   - CORS relaxes the same-origin policy; it does not protect the API.
     Non-browser clients ignore it, so authorization stays on the server.
   - Compare the request `Origin` exactly (scheme, host, and port) against a
     per-environment allowlist from configuration, and echo only the matched
     value. Never reflect an arbitrary `Origin` and never allow `null`
     (sandboxed frames and some redirects send it). Avoid suffix checks and
     unanchored regular expressions: `endswith("example.com")` accepts
     `evilexample.com`.
   - Send `Access-Control-Allow-Credentials: true` only with a specific
     allowed origin. Browsers refuse `*` with credentials; reflecting any
     origin with credentials is the real hole.
   - Send `Vary: Origin` on every response whose CORS headers depend on the
     origin, including the denied case, so shared caches do not serve one
     origin's response to another.
   - Answer preflight (`OPTIONS`) before authentication middleware, because
     preflights carry no credentials. List methods and headers explicitly: a
     `*` in `Access-Control-Allow-Headers` does not cover `Authorization` and
     does not apply to credentialed requests. Keep `Access-Control-Max-Age`
     modest; browsers cap it. Use `Access-Control-Expose-Headers` for response
     headers that scripts must read.
   - Prefer the framework's CORS middleware configured with the allowlist
     over hand-written headers.
4. **Roll out CSP in report-only mode first.**
   - Start with `Content-Security-Policy-Report-Only` and a reporting
     endpoint. Send both `report-uri` (deprecated, but some browsers support
     only it) and `report-to` with a `Reporting-Endpoints` header. They post
     different formats (`application/csp-report` and
     `application/reports+json`), so the endpoint accepts both. Reports are
     untrusted input: limit their size and rate, and strip query strings,
     which may hold tokens, before storing.
   - Prefer a strict policy: a fresh nonce per response (at least 128 bits
     from a CSPRNG) on every script tag, plus `'strict-dynamic'` so trusted
     scripts can load their dependencies. For static HTML that cannot carry a
     per-response nonce, such as a CDN-served app shell, use hashes
     (`'sha256-...'`) of its inline scripts instead. Never store a nonced page
     in a shared cache; a reused nonce protects nothing.
   - Always include `object-src 'none'`, `base-uri 'none'` (or `'self'`), and
     `frame-ancestors` (step 5). Add `default-src`, `connect-src`, `img-src`,
     `style-src`, `font-src`, and `form-action` as the inventory requires, and
     confirm that `form-action` permits any SSO form posts and redirects.
   - Fix violations at the source: move inline handlers to
     `addEventListener`, replace `javascript:` URLs, remove `eval`, or replace
     the library. Never add `'unsafe-inline'` or `'unsafe-eval'` to make
     reports stop. If a vendor truly requires one, record the exception, its
     owner, and the plan to remove it.
   - Collect reports over real traffic for the period the project's policy
     sets (for example one to two weeks), ignoring noise from browser
     extensions (`chrome-extension:` and `moz-extension:` sources). Then
     enforce with `Content-Security-Policy`, keeping a report-only header for
     the next tightening.
   - A `<meta>` CSP cannot set `frame-ancestors`, reporting, or `sandbox`; use
     the response header.
   - Optionally add Trusted Types (`require-trusted-types-for 'script'`) for
     DOM XSS sinks, report-only first; check current browser support.
5. **Control framing.** Use `frame-ancestors 'none'` unless the app must be
   embedded; then list the exact embedding origins or `'self'`. For older
   browsers also send `X-Frame-Options: DENY`, or `SAMEORIGIN` when only the
   app frames itself. It cannot express an allowlist, so when other origins may
   embed the app, rely on `frame-ancestors` alone; browsers that support
   `frame-ancestors` ignore `X-Frame-Options` when both are present. Give
   third-party iframes the app embeds a `sandbox` attribute and an `allow` list.
6. **Set the remaining headers.**
   - `Strict-Transport-Security`, sent only over HTTPS: start with a short
     `max-age` in production, raise it (for example to one year,
     `max-age=31536000`) once nothing breaks, add `includeSubDomains` only
     after confirming every subdomain serves HTTPS, and treat `preload` as
     close to irreversible, because removal from browser preload lists takes
     months. Check hstspreload.org for current preload requirements.
   - `X-Content-Type-Options: nosniff` on every response, with a correct
     `Content-Type` everywhere, because `nosniff` blocks scripts and styles
     served with the wrong type.
   - `Referrer-Policy: strict-origin-when-cross-origin`, or `no-referrer` on
     pages whose URLs carry tokens (reset and invitation links).
   - `Permissions-Policy` disabling features the app does not use, for example
     `camera=(), microphone=(), geolocation=()`.
   - `Cross-Origin-Opener-Policy: same-origin` on documents, or
     `same-origin-allow-popups` where OAuth or payment popups need
     `window.opener`. Add `Cross-Origin-Embedder-Policy` only when the app
     needs cross-origin isolation, and
     `Cross-Origin-Resource-Policy: same-origin` (or `same-site`) on sensitive
     resources.
   - Omit `X-XSS-Protection` or set it to `0`; the filter it controlled is
     obsolete.
7. **Audit every cookie.** List each `Set-Cookie` (session, CSRF, preferences,
   analytics) and give it `Secure`; `HttpOnly` unless scripts must read it; an
   explicit `SameSite`; the narrowest `Path`; no `Domain` unless subdomains
   need it; and the `__Host-` prefix where it can meet that prefix's rules
   (`Secure`, `Path=/`, no `Domain`). `SameSite=None` requires `Secure`. The
   session cookie follows the `implement-authentication` skill.
8. **Cover every response and environment.** Confirm the headers on error
   pages, redirects, static files, and responses generated by the proxy or
   CDN, which the application never sees. Keep per-environment values
   (allowed origins, report endpoint) in configuration, not code.

## Reference: CORS decision and target headers (illustrative)

The decision logic any middleware configuration should reproduce (Python):

```python
from __future__ import annotations

ALLOWED_ORIGINS = frozenset({  # per environment, loaded from configuration
    "https://app.example.com",
    "https://admin.example.com",
})


def cors_headers(origin: str | None, preflight: bool = False) -> dict[str, str]:
    """Exact match only: no reflection, no suffix match, no "null"."""
    headers = {"Vary": "Origin"}  # merge with any existing Vary value
    if origin is None or origin not in ALLOWED_ORIGINS:
        return headers  # no CORS headers: the browser blocks the read
    headers["Access-Control-Allow-Origin"] = origin
    headers["Access-Control-Allow-Credentials"] = "true"
    if preflight:
        headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE"
        headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRF-Token"
        headers["Access-Control-Max-Age"] = "600"
    return headers
```

A target set for HTML documents once report-only shows no unexplained
violations (`NONCE` is generated per response):

```text
Content-Security-Policy: script-src 'nonce-NONCE' 'strict-dynamic' https: 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; report-uri /csp-reports; report-to csp
Reporting-Endpoints: csp="https://app.example.com/csp-reports"
Strict-Transport-Security: max-age=31536000
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
X-Frame-Options: DENY
```

`https:` and `'unsafe-inline'` here are fallbacks for old browsers only:
browsers that support nonces ignore `'unsafe-inline'` when a nonce is present,
and browsers that support `'strict-dynamic'` ignore `https:`. Never use
`'unsafe-inline'` without a nonce or hash beside it. JSON API responses can
carry the tighter `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Production header changes are outward-facing: a wrong CSP breaks pages and a
  wrong HSTS value strands HTTP-only subdomains. Ship through the normal
  deploy with approval, and CSP in report-only mode first.
- Never enable HSTS `preload` or `includeSubDomains` without explicit approval
  and a confirmed inventory of subdomains.
- Never weaken a test, check, or threshold to make work pass. Never silence a
  violation with `'unsafe-inline'`, `'unsafe-eval'`, `*`, or a broad scheme
  source, and never reflect `Origin` or use `*` with credentials.
- Run external header scanners (for example Mozilla HTTP Observatory) only
  against URLs the user approves; they are outward-facing.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- **Header tests** per response type (HTML page, API, static file, error,
  redirect) assert the exact CSP header name and value, HSTS, `nosniff`,
  `Referrer-Policy`, `Permissions-Policy`, COOP, and `frame-ancestors` with
  `X-Frame-Options`.
- **CORS tests:** an allowed origin gets itself echoed, credentials allowed,
  and `Vary: Origin`; a disallowed origin, `null`, a look-alike such as
  `https://app.example.com.evil.test`, and `https://evilapp.example.com` get
  no `Access-Control-Allow-Origin`; an uncredentialed preflight from an
  allowed origin succeeds and lists the methods and headers.
- **CSP tests:** two responses carry different nonces; every script tag
  carries its response's nonce; the policy has no `'unsafe-eval'` and no
  `'unsafe-inline'` without a nonce or hash.
- **Browser check:** run the main journeys in a real browser, through the
  end-to-end suite (the `e2e-test-suite` skill) or by hand, and record
  `securitypolicyviolation` events or console CSP errors: none unexplained in
  report-only mode, none at all once enforced. Embedding the page from another
  origin is blocked.
- **Reporting:** the endpoint accepts and stores a test report in both
  formats.
- **Cookies:** each `Set-Cookie` carries the intended attributes.
- Type check, lint, and the full suite pass.

## Report

- **Inventory:** origins and embeds the app needs, with evidence.
- **CORS:** allowlist per environment, credentials, and preflight handling.
- **CSP:** the policy text, its mode, the nonce or hash strategy, exceptions
  with owners, and a summary of report triage.
- **Headers and cookies:** final values and the layer that sets each.
- **Rollout:** what ships now and what waits for approval (CSP enforcement
  date, HSTS ramp, `includeSubDomains`, `preload`).
- **Verification:** each test and browser check, with results.
- **Not verified:** environments, browsers, or layers (CDN, proxy) not
  checked, and why.

## Optional delegation

The `security-reviewer` subagent can review the CORS and CSP configuration
independently. The `infrastructure-reviewer` subagent can check headers set in
proxy, CDN, or platform configuration, the `frontend-builder` subagent can
refactor inline handlers and scripts so a strict policy fits, and the
`test-writer` subagent can add header and CORS tests. The workflow above stays
complete for a single agent.
