---
name: implement-authentication
description: "Implement sign-in, sessions, tokens, OAuth 2.x and OIDC or SAML single sign-on, password reset, MFA (TOTP, passkeys), and API keys on the framework's or a trusted provider's building blocks, with hardened cookies, CSRF defenses, strict token validation, session rotation, and a test per failure mode. Use when adding or changing login, logout, signup, sessions, JWT handling, SSO, password reset, MFA, or API keys. Not for permission models (use the access-control-design skill) or reviewing existing auth code (use the security-review skill)."
---

# Implement Authentication

Establish who is calling, keep that proof safe in transit and at rest, and end
it when it should end. The stance is **assemble, never invent**: every
cryptographic and protocol step comes from the framework's auth module or a
maintained provider or library, and every failure mode gets a test.

## When to use

- Adding or changing sign-in, sign-up, logout, sessions, remember-me, or token
  issuance and validation.
- Adding SSO through OAuth 2.x, OpenID Connect, or SAML, or switching identity
  providers.
- Adding password reset, email change, MFA (TOTP, WebAuthn or passkeys,
  recovery codes), or API keys.
- Fixing an auth defect: sessions that survive logout, account enumeration,
  missing CSRF protection, or tokens accepted that should be rejected.

## When not to use

- A new auth flow or provider with no design yet: use the `threat-modeling`
  skill first, then return here.
- Deciding what an authenticated caller may do (roles, ownership, tenants): use
  the `access-control-design` skill.
- Password-hashing parameters, encrypting stored secrets, or other cryptography:
  use the `cryptographic-protocol-implementation` skill.
- CORS, CSP, and other response headers: use the `browser-security-config` skill.
- Reviewing existing auth code without changing it: use the `security-review`
  skill.
- A signing key, client secret, or API key has leaked: use the
  `secret-leak-response` skill.

## Inputs to gather

Discover these from the repository first. Ask only about what remains ambiguous
and would change the design.

- **Stack:** the framework and its auth module (for example Django auth, Rails
  with Devise, Spring Security, ASP.NET Core Identity, Laravel, Auth.js, or
  Passport), the session store, the user table, and the stored password-hash
  format.
- **Identity provider**, if any (for example Auth0, Okta, Microsoft Entra ID,
  Amazon Cognito, or Keycloak), and the protocols it offers.
- **Clients:** server-rendered pages, a single-page app on the same site or
  another site, mobile apps, third-party API consumers, and services. Each one
  changes where credentials may live.
- **Policy:** session idle and absolute timeouts, MFA requirements, password
  rules, throttling limits, and audit retention. Use the project's policy; do
  not invent numbers.
- **Supporting systems:** email sending, a job queue, shared rate-limit storage
  (for example Redis), the audit log sink, and the secret manager.
- **Commands:** test, lint, and type-check commands from `AGENTS.md`,
  `CLAUDE.md`, package scripts, or the `Makefile`.

## Workflow

1. **Map the current flows.** List every way in: password login, SSO
   callbacks, API keys, token refresh, remember-me, magic links, reset links,
   admin login, and service tokens. For each, note where identity is
   established, where the credential is stored, and how it ends. A new flow
   without a threat model stops here for the `threat-modeling` skill.
2. **Use building blocks, not primitives.** Use the framework's auth module or
   the provider's SDK, and a maintained OIDC client (for example
   `openid-client` for Node, Authlib for Python, Spring Security OAuth2 Client,
   or the ASP.NET Core OpenID Connect handler). Never parse or verify JWTs by
   hand, generate tokens with non-cryptographic randomness, or compare secrets
   with `==`.
3. **Choose sessions or tokens per client.**
   - Browsers calling their own backend: a server-side session with an opaque
     random ID in a cookie. It is revocable and keeps tokens out of JavaScript.
   - Single-page apps on an OIDC provider: prefer a backend-for-frontend that
     runs the code flow and gives the browser only a session cookie. If tokens
     must reach the browser, keep a short-lived access token in memory. Never
     put long-lived access or refresh tokens in `localStorage` or
     `sessionStorage`, where any XSS can read them.
   - Mobile apps: the code flow with PKCE in the system browser, not an
     embedded web view, with tokens in the platform keystore (iOS Keychain,
     Android Keystore).
   - API consumers and services: short-lived provider-issued tokens, client
     credentials, workload identity, or API keys (step 13).
   - Self-issued JWTs used as browser sessions are hard to revoke. If you keep
     them, make them short-lived and check a server-side session or version on
     each request.
4. **Set cookie attributes deliberately.** A session cookie looks like
   `Set-Cookie: __Host-session=OPAQUE_ID; Path=/; Secure; HttpOnly; SameSite=Lax`.
   - `HttpOnly` hides it from scripts; `Secure` sends it only over HTTPS.
   - `SameSite=Lax` is a sound default; `Strict` suits high-risk apps that can
     lose the session on inbound links. Use `None` only when a cross-site
     context truly needs the cookie: it requires `Secure` and makes CSRF
     defense mandatory. Set it explicitly, because browser defaults differ.
   - The `__Host-` prefix makes browsers reject the cookie unless it is
     `Secure`, has `Path=/`, and has no `Domain`, so a sibling subdomain cannot
     set or overwrite it. Omit `Domain` unless subdomains must share it.
   - Enforce idle and absolute timeouts on the server; `Max-Age` is a hint.
5. **Defend cookie-authenticated writes against CSRF.**
   - Enable the framework's CSRF protection (synchronizer token or signed
     double-submit cookie) for every state-changing method, for example Django
     `CsrfViewMiddleware`, Rails `protect_from_forgery`, Spring Security CSRF,
     or ASP.NET Core antiforgery. Express has none built in and the old
     `csurf` package is deprecated, so choose a maintained one. Never change
     state on `GET` or `HEAD`.
   - Also reject cross-site state-changing requests by checking `Origin` or
     `Sec-Fetch-Site`. `SameSite` is defense in depth only: sibling subdomains
     count as same-site, and `Lax` still sends cookies on top-level `GET`.
   - Protect the login form as well; login CSRF signs the victim into the
     attacker's account.
   - An API that accepts credentials only in the `Authorization` header is not
     exposed to CSRF. Do not also accept the same credential from a cookie.
6. **Run OAuth and OIDC as the authorization code flow with PKCE.** Follow the
   provider's documentation and the OAuth 2.0 Security Best Current Practice
   (RFC 9700).
   - Use PKCE with `S256` for every client; RFC 9700 requires it for public
     clients and recommends it for confidential ones. Do not use the implicit
     or resource-owner password grants.
   - Generate `state`, `nonce`, and the PKCE verifier per attempt from a
     CSPRNG, bind them to the browser session (server-side or a short-lived
     encrypted cookie), check `state` first on the callback, and use them once.
   - Register exact redirect URIs, without wildcards. After login, redirect
     only to a same-origin path (one leading `/`, never `//`) or an
     allowlisted URL, never to an unchecked `next` parameter.
   - The ID token must have a valid signature from the issuer's published
     keys, an `iss` exactly equal to the expected issuer, an `aud` containing
     your client ID, an unexpired `exp`, and a `nonce` equal to the stored one.
     The library does this; a test proves it is switched on.
   - Identify users by issuer plus `sub`, never by email. Link an external
     identity to an existing account only after the user signs in to that
     account, never because the emails match; an unverified or reassigned
     email becomes an account takeover.
   - SAML: prefer a broker or a maintained library configured from the
     IdP's metadata, and keep it patched; XML signature handling has a long
     history of bypasses.
   - Refresh tokens for public clients: rotate on use with reuse detection, or
     sender-constrain them, where the provider supports it.
7. **Validate every JWT you accept** with a maintained library (example below).
   - An explicit algorithm allowlist that matches the issuer (for example
     `RS256` or `ES256`). Reject `none`, and never let the token header choose
     between symmetric and asymmetric algorithms.
   - Keys from your configured JWKS, selected by `kid`, cached, and refetched
     on an unknown `kid` with a rate limit. Ignore `jku`, `x5u`, and embedded
     `jwk` headers.
   - Signature, `exp`, `nbf` (with seconds of leeway for clock skew), exact
     `iss`, and `aud` containing this API. Reject ID tokens presented as access
     tokens, for example by checking the `at+jwt` type from RFC 9068 where the
     provider sets it.
   - Payloads are encoded, not encrypted; keep secrets and personal data out.
   - Output of decode-without-verify functions (`decode` in the
     `jsonwebtoken` package, PyJWT with `verify_signature` off) never feeds a
     decision.
8. **Manage the session lifecycle.**
   - Rotate the session ID on login, after MFA or step-up, and on any privilege
     change, to prevent fixation. Many frameworks rotate on login (Django
     `login()`, Spring Security's default fixation protection); confirm it,
     and call the explicit API elsewhere (for example `req.session.regenerate`
     in express-session, `reset_session` in Rails).
   - Logout destroys the server-side session and its refresh tokens, not only
     the cookie. For SSO, also end the provider session if the product needs it.
   - A password change or reset invalidates every other session, refresh
     token, and remember-me token for the user, and notifies the user. A "sign
     out everywhere" action does the same.
   - With stateless access tokens, revocation waits for expiry; keep lifetimes
     short and state the window in the report.
9. **Store passwords properly.** Hash with Argon2id through the framework's
   hasher or a maintained library, with parameters from the
   `cryptographic-protocol-implementation` skill. Rehash on login when
   parameters change, and upgrade legacy hashes at next login. Follow the
   project's policy or NIST SP 800-63B: a minimum length, a maximum of at least
   64 characters, screening against breached passwords, and no composition
   rules or forced periodic changes. Never log request bodies on auth routes.
10. **Build password reset without leaks.**
    - The same response, status, and timing whether or not the account exists
      ("If an account exists, we sent a link"). Send the email from a
      background job so timing does not differ.
    - A token of at least 128 bits from a CSPRNG, stored only as a hash, bound
      to one user, short-lived per policy (for example 15 to 60 minutes), and
      consumed atomically once. A new token or a password change invalidates
      older ones.
    - Build the link from a configured base URL, never from the request's
      `Host` header. Serve the reset page with `Referrer-Policy: no-referrer`
      and no third-party scripts.
    - After a reset, invalidate sessions (step 8) and send the user to normal
      sign-in, so a reset cannot skip MFA.
    - Apply the same rules to email verification, magic links, and invitations.
11. **Throttle without handing attackers a lockout button.**
    - Rate-limit login, MFA verification, reset requests, signup, and failed
      API-key use per account and per source address, in storage shared by all
      instances, using the project's limits (for example progressive delays
      after five failures for one account in fifteen minutes).
    - Prefer delays, challenges, and temporary blocks per account and address
      over hard account lockout, which lets anyone lock out a victim. Return
      `429` with `Retry-After`.
    - Keep failures generic ("Incorrect email or password"). When the account
      does not exist, still verify against a fixed dummy hash so the response
      time does not reveal it.
12. **Add MFA with a recovery path that is not a bypass.**
    - TOTP (RFC 6238) through a library (for example pyotp or otplib): generate
      the secret on the server, encrypt it at rest (it must stay readable, so it
      cannot be hashed), confirm enrollment with one valid code, allow at most
      one step of clock drift, reject a reused code, and rate-limit attempts.
    - WebAuthn and passkeys through a maintained server library (for example
      SimpleWebAuthn, py_webauthn, or Yubico's java-webauthn-server):
      single-use server-side challenges, verified origin and RP ID, user
      verification where policy requires it, and the library's guidance on
      signature counters (synced passkeys often report 0).
    - Recovery codes: a set (for example ten) of random codes shown once,
      stored hashed, each single use; regenerating replaces the whole set.
    - Require recent re-authentication to change the password, email, MFA
      settings, or API keys, and notify the user of each change. Treat SMS
      codes as a weaker factor per policy. Support-desk MFA resets need
      identity verification and an audit event.
13. **Issue API keys you can find, scope, and rotate.**
    - Format: an identifiable prefix (so secret scanners can match it), a
      public key ID, and at least 128 bits of random secret. Show it once.
    - Store the key ID and a SHA-256 hash of the secret. A fast hash is enough
      because the secret is random, unlike a password. Compare in constant time.
    - Each key has an owner, a tenant, least-privilege scopes, an optional
      expiry, and a last-used time. Allow two active keys during rotation, and
      make revocation take effect immediately.
    - Accept keys only in a header, never in query strings that end up in logs.
14. **Emit audit events** for login success and failure, logout, MFA
    enrollment, removal, and recovery-code use, password change and reset,
    email change, session revocation, SSO linking, and API key creation,
    rotation, and revocation. Record actor, subject, action, result, time,
    source address, user agent, and request ID; never passwords, codes, tokens,
    session IDs, or reset links. Use the `observability-setup` skill to alert
    on spikes.
15. **Test every failure mode** at the HTTP seam (list under Verification).
    Where practical, show each test failing against the unprotected behavior.

## Worked example: reset tokens and JWT validation (illustrative Python)

Standard library plus PyJWT 2.x. The issuer, audience, and JWKS URL come from
the provider's discovery document; these values are placeholders.

```python
from __future__ import annotations

import hashlib
import secrets

import jwt
from jwt import PyJWKClient


def new_reset_token() -> tuple[str, str]:
    """Return (token for the emailed link, SHA-256 hash to store)."""
    token = secrets.token_urlsafe(32)  # 256 bits from the OS CSPRNG
    return token, hashlib.sha256(token.encode("ascii")).hexdigest()


ISSUER = "https://id.example.com/"  # exact string, including any trailing slash
AUDIENCE = "https://api.example.com"
JWKS = PyJWKClient("https://id.example.com/.well-known/jwks.json")


def verify_access_token(token: str) -> dict:
    """Return the claims, or raise jwt.PyJWTError if any check fails."""
    signing_key = JWKS.get_signing_key_from_jwt(token)  # selected by kid
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],  # allowlist; never taken from the token header
        audience=AUDIENCE,
        issuer=ISSUER,
        leeway=30,  # seconds of clock skew for exp and nbf
        options={"require": ["exp", "iss", "aud", "sub"]},
    )
```

Consume a reset token in one atomic statement (PostgreSQL), so two concurrent
requests cannot both use it:

```sql
UPDATE password_reset_tokens
   SET used_at = now()
 WHERE token_hash = $1  -- SHA-256 of the presented token
   AND used_at IS NULL
   AND expires_at > now()
RETURNING user_id;
```

No row means "this link is invalid or has expired", without saying which. In
the same transaction, store the new password hash, delete the user's other
reset tokens, and revoke their sessions. API keys follow the same pattern:
look up the record by key ID, then compare hashes with `hmac.compare_digest`.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  changing identity-provider settings or redirect URIs, changing production
  session or cookie settings, or revoking every user's sessions.
- Never weaken a test, check, or threshold to make work pass.
- Never hand-roll cryptography, JWT parsing, or OAuth, OIDC, or SAML protocol
  steps. Never disable signature, issuer, audience, expiry, or TLS checks,
  even temporarily; test-only shortcuts live in test configuration that
  production cannot load.
- Never log, echo, or commit passwords, tokens, codes, session IDs, reset
  links, client secrets, or signing keys. Keep secrets in the secret manager
  (the `config-and-secrets` skill) and use placeholders in examples.
- Never test against real user accounts or a production identity tenant; use a
  local fake provider, the library's test helpers, or a sandbox tenant.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

Failure-mode tests, each one named and passing:

- **Sessions:** the ID changes after login and step-up; the old ID is rejected
  after logout; other sessions are rejected after a password change or reset.
- **Cookies:** `Set-Cookie` carries `Secure`, `HttpOnly`, an explicit
  `SameSite`, `Path=/`, and the `__Host-` prefix where used.
- **CSRF:** a state-changing request with a missing or wrong token, or a
  cross-site `Origin`, is rejected; no `GET` changes state.
- **OIDC callback:** a missing, mismatched, or replayed `state`, a wrong
  `nonce`, a wrong `iss` or `aud`, an expired ID token, and a post-login
  redirect to an external or protocol-relative URL are each rejected.
- **JWT:** `alg` set to `none`, an HS256 token signed with the public key, an
  unknown `kid`, an expired token, a future `nbf`, a wrong `iss` or `aud`, an
  ID token sent to the API, and a tampered payload are each rejected.
- **Reset:** responses for existing and unknown accounts match; a token works
  once; expired, reused, and superseded tokens fail; a forged `Host` header
  does not change the emailed link.
- **Throttling:** limits trigger per account and per address with `429`, and
  failures from one address do not hard-lock the victim's account.
- **MFA:** wrong, reused, and out-of-window codes fail; recovery codes work
  once; MFA changes require step-up; a reset does not bypass MFA.
- **API keys:** revoked, expired, and out-of-scope keys fail; a key in a query
  string is rejected; the database stores only the hash.
- **Logs:** output from the test run contains no passwords, tokens, codes, or
  session IDs.

Then run the type check, lint, and full suite. In a local or staging browser,
confirm cookie attributes in the developer tools, and sign in and out in two
browsers to confirm that logout and password change end the other session.

## Report

- **Flows:** what was added or changed, and the libraries and versions used.
- **Credential storage:** per client type, with cookie attributes.
- **Protocol checks:** PKCE, `state`, `nonce`, redirect handling, and token
  validation settings (algorithms, issuer, audience, leeway).
- **Lifecycle:** rotation points, logout, invalidation on password change,
  timeouts, and the revocation window for stateless tokens.
- **Abuse controls:** throttling, enumeration handling, MFA, and recovery.
- **Audit events:** events added and their fields.
- **Verification:** each failure-mode test and command, with results.
- **Not verified:** provider behavior taken from documentation only,
  production configuration, and anything else not exercised.

## Optional delegation

Auth changes warrant a second pass: delegate an independent review to the
`security-reviewer` subagent before merging. The `docs-researcher` subagent can
look up version-exact provider and library documentation, the `test-writer`
subagent can write the failure-mode tests, and the `backend-builder` subagent
can implement a bounded slice; rerun their checks yourself. The workflow above
stays complete for a single agent.
