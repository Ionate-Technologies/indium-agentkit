---
name: feature-flag-lifecycle
description: "Add, roll out, and remove feature flags and kill switches with the project's flag system (LaunchDarkly, Unleash, Flagsmith, OpenFeature, a config service, or an in-house table): owners and expiry dates, safe defaults when the service is unreachable, server-side gating, one decision point, both paths tested, staged rollout, and cleanup in a safe order. Use when adding a flag, ramping a percentage rollout, testing a kill switch, or removing stale flags. Not for deploy canaries (use the deployment-safety skill)."
---

# Feature Flag Lifecycle

Add a flag with an owner and an end date, roll it out in measured steps, and
remove it once it has done its job. The stance is **every flag is temporary
debt with a safe default**: when the flag service is unreachable the code falls
back to the old, safe behavior, and a flag leaves the code before it leaves the
flag service.

## When to use

- Shipping a risky change dark behind a release flag for a staged rollout, or
  adding an operational kill switch for a feature or dependency.
- Running an experiment that needs consistent assignment, or gating a feature
  by plan, tenant, or role.
- Removing a flag that reached 100 percent or ended its experiment, or
  auditing stale flags.

## When not to use

- Planning the deploy itself (canaries, health gates, rollback): use the
  `deployment-safety` skill; this skill plugs flag steps into that plan.
- Experiment metrics, exposure events, and analysis: use the
  `product-analytics` skill.
- Permanent access rules or entitlements: use the `access-control-design`
  skill. A flag service is not an authorization system.
- Store releases and mobile halts: use the `mobile-release-safety` skill
  alongside this one.
- SDK keys and other static configuration: use the `config-and-secrets` skill.

## Inputs to gather

Discover these from the repository and the flag service before asking. Ask the
user only about what remains ambiguous and would change the result.

- The flag system and SDK versions, and how values reach each service and
  client (streaming, polling, a bootstrap file, or a relay).
- Existing conventions: naming, a registry or constants module, owner and
  expiry fields, and how tests set flag values.
- Who may change flags per environment, whether changes are audited, and
  whether production changes need approval.
- The stable bucketing key (user, account or tenant, or device ID for
  signed-out users), and the health gates and analytics events that apply.
- For removal: serving values per environment and segment, evaluation
  statistics, and every repository, service, and app version that reads it.

## Workflow

### Flag types

| Type | Purpose | Expected life | Code default |
| --- | --- | --- | --- |
| Release | Ship dark, then roll out | Days to weeks | Off: the old path |
| Experiment | Compare variants | Until the decision | Control |
| Ops kill switch | Turn off a feature or dependency under failure or load | Long-lived, reviewed | The normal running state (step 3) |
| Permission | Gate by plan, tenant, or role | Long-lived, reviewed | Deny |

### Add a flag

1. **Name and register it.** Follow the project's convention; if there is
   none, propose `area.purpose` in kebab case, for example
   `checkout.new-tax-engine`. Record the type, an owning team, the creation
   date, an expiry or review date, and a cleanup ticket, in the flag service's
   metadata and in code (a constants module or registry). Reference each key
   through one constant; never build keys from strings at runtime, because that
   defeats the search during cleanup. Name flags for the on state
   (`new-tax-engine`, not `disable-old-tax`); inverted names cause inverted
   cleanups.
2. **Evaluate on the server for anything that matters.** If a flag gates data,
   money, or authorization, evaluate it on the server and enforce the result
   there. Client-side flags are UI hints only: users can read and change them,
   and client SDKs often receive every flag value for the user. Keep secrets
   and unreleased customer names out of flag variations. Client SDKs use a key
   meant to be public; never ship a server SDK key to a browser or app.
3. **Choose the default for an outage.** The code default is what runs when the
   SDK has not initialized, the service is unreachable, or the flag was
   deleted. Release and experiment flags default to the old path or control;
   permission flags default to deny. A kill switch defaults to the state that
   keeps the product working, usually the feature running, unless the feature
   itself is the hazard; write the choice next to the flag. Then check the SDK:
   whether it serves cached last-known values, how long initialization can
   block startup (set a bounded wait), and whether it raises or returns the
   default on errors. The OpenFeature evaluation API returns the default instead
   of throwing; wrap vendor calls that can raise.
4. **Make one decision point.** Evaluate the flag once per request or
   operation, at the edge (route handler, job entry point, composition root),
   and pass the decision inward as a parameter or a chosen implementation. Do
   not scatter checks through inner logic; two evaluations in one request can
   disagree while targeting changes. Keep the old and new paths as whole units
   (two functions or classes) so that cleanup deletes one unit. If the flag
   changes a cached response, the cache key must include the variant; see the
   `add-caching` skill.
5. **Bucket consistently.** Pass the same stable targeting key from every
   service and client that evaluates the flag, so one user or tenant sees one
   variant everywhere. In B2B products, bucket by account so a whole
   organization switches together. A signed-out device ID that changes at
   sign-in moves people between buckets; decide how to handle that. In-house
   bucketing must hash the flag key plus the stable ID with a stable hash
   (example below), never a per-process randomized hash such as Python's
   built-in `hash()`.
6. **Keep both paths data-compatible.** While the flag can flip either way, the
   old path must read whatever the new path writes. Ship schema or format
   changes with the `safe-migration` skill's expand and contract steps; a flag
   does not make a migration reversible.
7. **Test both paths.** Parametrize the affected tests over on and off (or each
   variant), plus an evaluation failure that must produce the code default. Use
   the SDK's test or in-memory provider, or a fake client, never the live
   service. Test flags together only where they share a code path, and avoid
   nesting flags.

### Roll out

8. **Ramp in steps tied to health gates.** A typical path: on in development
   and staging, then internal users, a beta segment, and percentages such as 1,
   5, 25, 50, and 100, holding at each step long enough to read the signals.
   Use the gates and abort thresholds from the `deployment-safety` skill,
   compare the on and off cohorts, and turn the flag off at the first breach.
   Every production flag change is a production change: get approval and make
   sure the change is recorded (the flag service's audit log or the deploy
   log). Most providers keep people in the rollout as the percentage grows,
   provided the bucketing key and seed stay the same; confirm this for yours,
   and never reshuffle an experiment midway.
9. **Test kill switches before you need them.** In staging, and with approval
   in production at low traffic, flip the switch and measure how long every
   service and client takes to obey it. Streaming SDKs update quickly, polling
   SDKs wait for their interval, application caches add delay, and mobile
   remote config may refresh only at launch or after hours (check the client's
   fetch interval). Confirm the off state degrades gracefully, then record the
   steps and the measured propagation time in the service runbook with the
   `write-runbook` skill.

### Remove a flag

10. **Decide the winner from evidence.** The winner is what production actually
    serves, checked per environment and per segment, not the flag's name or its
    off variation. A release flag is ready when it has served 100 percent for
    the agreed soak period with healthy metrics; an experiment when its analysis
    is decided. Get the owner's confirmation.
11. **Remove it from code first.** In one focused change, make the winning path
    unconditional, delete the losing branch and helpers that only it used,
    reduce the parametrized tests to the winning path, and delete the flag
    constant and registry entry. Use the `refactor-code` skill to keep the
    change behavior-preserving. Search every repository, service, mobile app,
    infrastructure definition, script, and dashboard for the key, then ship the
    change to every service.
12. **Then remove it from the flag service.** Only when no deployed code
    evaluates the flag: the service shows no recent evaluations (where it
    reports them), and app versions that read it have fallen below the agreed
    support threshold. Archive or delete it with approval. In the reverse
    order, every SDK falls back to the code default, which silently returns
    everyone to the old path.
13. **Track stale flags.** Keep the inventory current (owner, type, created,
    expiry). Propose a scheduled check or CI warning that lists flags past
    expiry or at 100 percent beyond the soak period, and use the provider's
    stale-flag or code-reference features if it has them. Long-lived kill
    switches and permission flags get a periodic review instead of an expiry.

## Worked example: one decision point with a safe default (illustrative Python)

`FlagClient` stands in for the project's SDK or OpenFeature client. The
handler decides once and passes the chosen implementation inward; cleanup
deletes one function and one line.

```python
from __future__ import annotations

import hashlib
import logging
from typing import Callable, Protocol

log = logging.getLogger(__name__)

# Release flag. Owner: payments team. Expires 2026-12-31. Cleanup: PAY-123.
NEW_TAX_ENGINE = "checkout.new-tax-engine"


class FlagClient(Protocol):
    def get_bool(self, key: str, default: bool, *, targeting_key: str) -> bool: ...


def new_tax_engine_enabled(flags: FlagClient, account_id: str) -> bool:
    """The only evaluation of NEW_TAX_ENGINE. Any failure means the old engine."""
    try:
        return flags.get_bool(NEW_TAX_ENGINE, False, targeting_key=account_id)
    except Exception:  # some SDKs raise instead of returning the default
        log.warning("flag evaluation failed; using default", extra={"flag": NEW_TAX_ENGINE})
        return False


def legacy_tax(subtotal_cents: int) -> int:
    return subtotal_cents * 8 // 100


def new_tax(subtotal_cents: int) -> int:
    return (subtotal_cents * 8 + 50) // 100  # rounds half up instead of down


def checkout_total(flags: FlagClient, account_id: str, subtotal_cents: int) -> int:
    # Decide once at the edge, then pass the chosen implementation inward.
    tax: Callable[[int], int] = (
        new_tax if new_tax_engine_enabled(flags, account_id) else legacy_tax
    )
    return subtotal_cents + tax(subtotal_cents)


def in_rollout(flag_key: str, stable_id: str, percent: float) -> bool:
    """In-house bucketing that agrees across processes, services, and restarts."""
    digest = hashlib.sha256(f"{flag_key}:{stable_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10_000  # steps of 0.01 percent
    return bucket < percent * 100
```

Tests call `checkout_total` with a fake client returning `True`, one returning
`False`, and one that raises, and assert the legacy result for the last. Salting
the hash with the flag key gives each flag an independent cohort, and raising
`percent` keeps everyone already included.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  For flags that means every change outside local and test environments:
  creating, retargeting, ramping, flipping, archiving, or deleting flags, and
  changing SDK keys or flag-service settings.
- Never weaken a test, check, or threshold to make work pass.
- Never use a client-side flag as access control, never put a server SDK key
  in client code, and never reuse a flag key for a new purpose.
- Never delete a flag from the flag service while deployed code or a supported
  app version still evaluates it.
- Do not log full evaluation contexts that contain personal data; log the flag
  key, the variant, and an identifier the privacy policy allows.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Tests for on, off, each variant, and evaluation failure pass, and failure
  produces the documented default.
- A search for the key finds one constant and one evaluation site per service.
- With the SDK uninitialized or pointed at an unreachable endpoint in a test,
  the service starts within its startup budget and serves the default path.
- Rollout: gate readings are recorded for each step, and the kill switch
  propagation time was measured.
- Removal: searches across repositories find no references, the full test
  suite passes without the flag, and the flag service showed no evaluations for
  the agreed period before archiving.

## Report

- **Flag:** key, type, owner, code default and why, expiry, cleanup ticket.
- **Decision point:** `path:line` per service, and the targeting key.
- **Tests:** paths covered, including the failure default.
- **Rollout:** steps, gate results, approvals, and who changed the flag.
- **Kill switch:** measured propagation time and the runbook entry.
- **Removal:** evidence for the winning path, the code change, and the
  flag-service state.
- **Not verified:** checks that could not run and why (for example no access
  to production evaluation statistics).

## Optional delegation

The `test-writer` subagent can add the parametrized on, off, and failure tests.
The `reviewer` subagent can check that a removal kept the winning branch and
deleted only dead code. The `security-reviewer` subagent can confirm that
permission flags are enforced on the server. The `mobile-specialist` subagent
can audit remote-config defaults and refresh behavior in a mobile release. The
workflow above stays complete for a single agent.
