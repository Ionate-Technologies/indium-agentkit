---
name: config-and-secrets
description: "Set up or restructure application configuration and secrets: one typed config module validated at startup, documented precedence, per-environment values instead of environment-name branches, secrets injected from a secret manager, nothing secret in client bundles or images, safe production defaults, rotation, and redaction. Use when adding settings or environment variables, adopting a secret manager, or cleaning up scattered config. Not for a credential that already leaked (use the secret-leak-response skill)."
---

# Config and Secrets

Give the application one validated source of configuration and a secret supply
that never travels with the code. The stance is **fail fast, never leak**: a
bad or missing key stops startup with a clear message, and a secret never lands
in the repository, an image, a client bundle, or a log.

## When to use

- Adding a setting, environment variable, or credential to a service.
- Config is read ad hoc across the codebase, defaults disagree between call
  sites, or a missing key crashes deep inside a request instead of at startup.
- Moving secrets out of committed files, CI variables, or images into a secret
  manager, or adding rotation.
- A frontend or mobile build may be shipping a secret through a public prefix.
- Setting production defaults for debug mode, auth, and error detail.

## When not to use

- A secret is already exposed: use the `secret-leak-response` skill first, then
  return here for the long-term structure.
- Dockerfiles and image hardening: use the `containerize-service` skill.
- CI secrets, OIDC federation, and workflow permissions: use the `ci-pipeline`
  skill.
- Renaming or removing keys that running deploys still read: use the
  `safe-migration` skill.
- Runtime toggles and kill switches: use the `feature-flag-lifecycle` skill.
- Provisioning the secret manager, IAM, or cluster resources: use the
  `infrastructure-as-code` or `kubernetes-workloads` skill.
- Encryption keys and key derivation: use the
  `cryptographic-protocol-implementation` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- Language, framework, and the validation library already in use (for example
  pydantic-settings, zod, envalid, Go envconfig, Spring
  `@ConfigurationProperties`, .NET options validation). Use it; do not add a
  second one.
- Every config read: search for `os.environ`, `os.getenv`, `process.env`,
  `import.meta.env`, `System.getenv`, `os.Getenv`, and `ENV[`, plus config
  files, `.env*` files, Compose files, Helm values, and CI workflows.
- How secrets reach the process today: a secret manager, Kubernetes Secrets, the
  platform's secret references, CI secrets, or files.
- Environments (local, test, preview, staging, production) and who owns each
  secret.
- Client build tools and their public prefixes; logging and error-reporting
  libraries and their redaction hooks.

## Workflow

1. **Inventory every key.** Record name, type, required or optional, default,
   secret or not, where it is read (`path:line`), where it is set per
   environment, and owner. Flag keys read in several places, defaults that
   differ, keys read but never set, and keys set but never read. If a real
   secret is committed, stop and use the `secret-leak-response` skill.
2. **Classify each key** as secret (passwords, tokens, signing keys, webhook
   secrets, private keys, connection strings with credentials), internal, or
   public (safe to ship to clients), and as build time or runtime. A database
   URL with an embedded password is a secret as a whole.
3. **Create one typed config module.** It loads, parses, and validates
   everything once at startup and exposes an immutable typed object. Nothing
   else reads the environment; enforce that with a lint rule or a test that
   searches for direct reads outside the module.
   - Parse real types (integers, URLs, enums, durations). Accept booleans only
     from an explicit set; in Python, `bool("false")` is `True`.
   - Validate before serving traffic or consuming jobs. On failure, exit
     non-zero with one message listing every missing or invalid key by name and
     reason, never by value.
   - Library error text can echo inputs: pydantic's default `ValidationError`
     text includes input values, and some zod messages (for example enum errors
     in zod 3) include the received value. Build the message from each error's
     location and type instead.
   - Wrap secrets in a type that masks them in `repr` and logs (pydantic
     `SecretStr`, or a small wrapper as in the example below).
4. **Document precedence**, lowest to highest, in the module and the config
   docs, for example code defaults, committed non-secret config files,
   environment variables, then the secret manager. Keep `.env.example` in sync
   with the module.
5. **Express environments as values, not branches.** Replace
   `if env == "production"` with explicit keys such as `LOG_LEVEL`,
   `COOKIE_SECURE`, or `PAYMENTS_BASE_URL`. An `APP_ENV` value may select a
   file or label telemetry, but behavior follows keys, so staging and previews
   differ only in data and production behavior stays testable.
6. **Load secrets from the platform.** Prefer injection by the platform or an
   SDK read at startup from HashiCorp Vault, AWS Secrets Manager or SSM
   Parameter Store, GCP Secret Manager, or Azure Key Vault. On Kubernetes, sync
   from the manager with External Secrets Operator or mount with the Secrets
   Store CSI Driver; a plain Secret manifest is only base64-encoded, so never
   commit one unencrypted. Authenticate with workload identity (IAM roles,
   workload identity federation, managed identity), not a stored bootstrap key.
   - Locally, use a gitignored `.env` or a developer secret-manager profile.
     Commit `.env.example` with names and obviously fake values, ignore `.env`
     and `.env.*`, and re-include the example with `!.env.example`.
7. **Keep secrets out of clients.** Prefixed variables are compiled into the
   bundle and readable by anyone: `NEXT_PUBLIC_` (Next.js), `VITE_` (Vite, or
   its configured `envPrefix`), `NUXT_PUBLIC_` (Nuxt public runtime config),
   `EXPO_PUBLIC_` (Expo), `PUBLIC_` (SvelteKit and Astro), and `REACT_APP_`
   (Create React App). Anything in a mobile binary or its plist, manifest, or
   build config is public too. Import the config module only from server code;
   in Next.js, the `server-only` package turns a client import into a build
   error. When a client needs a privileged call, proxy it through the backend
   or issue a short-lived, narrowly scoped token.
8. **Keep secrets out of images and build arguments.** No secrets in `ARG`,
   `ENV`, copied `.env` files, or the build context; build-time credentials use
   BuildKit secret mounts and runtime secrets are injected at deploy. Use the
   `containerize-service` skill for the Dockerfile and the `ci-pipeline` skill
   for CI secrets.
9. **Make defaults production-safe.** Debug off, auth on, verbose errors and
   stack traces off, secure cookies on, TLS verification on, admin and debug
   endpoints disabled. Development opts in explicitly. A missing required
   secret fails startup; never fall back to a development value such as
   `os.getenv("SECRET_KEY", "dev")`.
10. **Support rotation.** Read secrets at use with a short cache, or reload on
    a signal or file change. On Kubernetes, environment variables from a Secret
    change only on restart; mounted Secret files update after a delay, except
    `subPath` mounts. For secrets you verify (webhook signatures, session or
    token signing, inbound API keys), accept the current and previous value
    during rotation and sign only with the newest; key IDs make this explicit.
    For credentials you present, use the provider's dual-credential or
    alternating-user rotation where offered. Write the sequence down: create,
    deploy or reload, verify, revoke the old value.
11. **Redact everywhere.** Configure the logger and error reporter to scrub
    keys such as `password`, `token`, `secret`, `authorization`, `cookie`, and
    `api_key`, using the error reporter's own scrubbing hooks. At startup, log
    which keys loaded and from which source, never the values or the raw
    config object. Keep secrets out of URLs, because query strings reach access
    logs.
12. **Rename keys across deploys safely.** Read the new key with a fallback to
    the old one and a deprecation warning, set the new key everywhere, then
    remove the fallback and the old key. Use the `safe-migration` skill to stage
    it while old versions still run.
13. **Test and document.** Add the tests under Verification; update
    `.env.example`, the config reference, and the rotation notes.

## Worked example: validated loader with redaction (illustrative Python)

A dependency-free sketch of the required properties. In a project with
pydantic-settings, zod, or similar, use that library and keep the same
behavior: all errors at once, names but no values, masked secrets.

```python
"""Load, validate, and expose settings once, at startup (illustrative)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Mapping


class Secret:
    """Holds a secret; repr and str never show the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('****')"

    __str__ = __repr__


@dataclass(frozen=True)
class Settings:
    database_url: Secret
    signing_keys: tuple[Secret, ...]  # newest first; sign with [0], verify with any
    port: int = 8080
    debug: bool = False  # production-safe default; development opts in


BOOLS = {"true": True, "1": True, "false": False, "0": False}


def load_settings(env: Mapping[str, str]) -> Settings:
    errors: list[str] = []  # key names and reasons only, never values

    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        errors.append("DATABASE_URL: required")
    keys = [k.strip() for k in env.get("SIGNING_KEYS", "").split(",") if k.strip()]
    if not keys:
        errors.append("SIGNING_KEYS: required (comma-separated, newest first)")

    port = 8080
    raw_port = env.get("PORT", "").strip()
    if raw_port:
        if raw_port.isascii() and raw_port.isdigit() and 0 < int(raw_port) < 65536:
            port = int(raw_port)
        else:
            errors.append("PORT: must be an integer from 1 to 65535")

    debug = BOOLS.get(env.get("DEBUG", "false").strip().lower())
    if debug is None:
        errors.append("DEBUG: must be true, false, 1, or 0")

    if errors:
        raise ValueError("invalid configuration:\n  " + "\n  ".join(errors))
    return Settings(Secret(database_url), tuple(Secret(k) for k in keys), port, bool(debug))


if __name__ == "__main__":
    try:
        settings = load_settings(os.environ)
    except ValueError as exc:
        sys.exit(str(exc))  # exits non-zero before serving any traffic
    print(settings)  # Settings(database_url=Secret('****'), ...)
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  writing or deleting values in a shared secret manager, changing production
  environment settings, or revoking a credential.
- Never weaken a test, check, or threshold to make work pass.
- Never print, log, or paste a secret value, including in error messages, test
  output, or the report. Refer to it by key name.
- Never commit real values to `.env`, config files, fixtures, Helm values, or
  Secret manifests, and never give a secret a public client prefix.
- Never add a silent fallback from a missing production secret to a default.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Loader tests pass: all missing keys listed in one error, invalid types
  rejected, defaults production-safe, and a sentinel secret value absent from
  the error text, `repr`, and captured logs.
- Starting the service with required keys unset exits non-zero and names them.
- No direct environment reads remain outside the config module, apart from a
  documented allowlist.
- A client build made with a sentinel secret set contains neither the sentinel
  nor the secret key names (search the build output).
- `git check-ignore -v .env` shows the ignore rule, `.env.example` is tracked,
  and the project's secret scanner passes.
- Image metadata and history show no secrets (see the `containerize-service`
  skill), and rotation tests show two keys verify while only the newest signs.

## Report

- **Inventory:** keys by class, with sources and owners; conflicts resolved.
- **Config module:** location, library, precedence, and what fails at startup.
- **Secrets:** source per environment, identity used to read them, and
  `.env.example` and ignore rules.
- **Client and image exposure:** prefixed keys reviewed, build-output check, and
  image check.
- **Defaults, rotation, and redaction:** production defaults, rotation steps,
  and scrubbing configured.
- **Key renames:** staged plan or none.
- **Verification:** each command and its result.
- **Not verified:** environments or platforms not checked and why.

## Optional delegation

The `security-reviewer` subagent can review secret handling and client exposure.
The `infrastructure-reviewer` subagent can check secret-manager, IAM, and
cluster configuration, and the `migration-planner` subagent can stage key
renames. The `test-writer` subagent can write the loader tests. One agent can
complete this workflow alone.
