---
name: access-control-design
description: "Design and implement a permission model (RBAC, ABAC, or relationship-based) with tenant isolation, enforced deny-by-default in one policy layer that every handler, resolver, job, export, search, and admin tool calls, backed by data-layer tenant scoping and a who-can-do-what test matrix in CI. Use when adding roles, permissions, sharing, multi-tenancy, impersonation, or support access, or fixing IDOR or cross-tenant leaks. Not for sign-in and sessions (use the implement-authentication skill) or reviewing existing code (use the security-review skill)."
---

# Access Control Design

Decide who may do what to which resource in which tenant, in one place, and
prove it with a matrix. The stance is **deny by default, decide centrally,
enforce twice**: one policy layer makes every decision, the data layer
independently refuses cross-tenant rows, and a test matrix fails CI when
either drifts.

## When to use

- Adding roles, permissions, sharing, teams, organizations, or multi-tenancy.
- An IDOR, cross-tenant leak, or privilege escalation was found, or checks live
  only in the UI or are scattered across handlers.
- Adding admin tools, support access, impersonation, exports, search, or
  background jobs that touch tenant data.
- Replacing hard-coded role names with configurable roles, or adopting a policy
  engine.

## When not to use

- Sign-in, sessions, tokens, and MFA: use the `implement-authentication` skill.
- Designing the tables, keys, and indexes: use the `database-design` skill, and
  roll out row-level security or tenant columns on existing tables with the
  `safe-migration` skill.
- Implementing an endpoint once the policy exists: use the `backend-api` skill.
- Reviewing existing authorization without changing it: use the
  `security-review` skill or delegate to the `security-reviewer` subagent.

## Inputs to gather

Discover these from the repository first. Ask only about what remains ambiguous
and would change the model.

- **Tenancy model:** shared tables with a tenant column, a schema per tenant,
  or a database per tenant, and how a request's tenant is determined
  (subdomain, path, token claim, or membership lookup).
- **Principals:** users, service accounts, API keys, background jobs, support
  staff, and guests on shared resources.
- **Resources and actions:** the nouns and verbs, and the rules that depend on
  attributes such as owner, status, amount, or department.
- **Existing checks:** search for role-name comparisons (`role == "admin"`,
  `is_admin`, `isAdmin`), auth decorators and middleware, policy classes, and
  checks that exist only in the UI.
- **Tools already in use:** framework policy libraries (for example Pundit or
  CanCanCan, Django permissions or django-rules, Spring Security method
  security, ASP.NET Core authorization policies, CASL) or policy engines (for
  example OPA, Cedar, OpenFGA, SpiceDB, Casbin).
- **Data layer:** database, ORM, and whether PostgreSQL row-level security is
  available.
- **Policy and commands:** audit and support-access requirements, and the
  project's test commands from `AGENTS.md`, `CLAUDE.md`, package scripts, or the
  `Makefile`.

## Workflow

1. **Inventory every entry point.** HTTP routes; GraphQL queries, mutations,
   and field resolvers, including global `node(id:)` lookups; RPC and websocket
   handlers; queue consumers and scheduled jobs; webhooks; exports and reports;
   search; file and object downloads, including signed URLs; admin consoles;
   management commands; data pipelines; and LLM tools. For each, record the
   actor, action, resource, how the tenant and resource are loaded, and the
   current check. Non-HTTP paths are where tenant filters usually go missing.
2. **Write the requirements as a matrix before choosing a model.** Rows are
   actors (anonymous, member by role, resource owner, other-tenant user,
   service account, support agent, suspended user), columns are actions per
   resource type, and cells are allow, deny, or a stated condition. Ask the
   product owner only about cells that existing behavior cannot answer.
3. **Choose the simplest model that expresses the matrix.**
   - **RBAC:** roles per tenant membership (user, tenant, role) with
     permissions attached to roles. Fits most business applications.
   - **ABAC:** conditions on actor, resource, and context attributes (owner,
     status, amount limit, time). Usually layered on RBAC in the same policy.
   - **Relationship-based** (Zanzibar-style, for example OpenFGA or SpiceDB):
     per-object sharing, nested groups, and inherited folder access. It adds a
     service and a relationship store that must stay in sync with your writes;
     read the engine's consistency options before relying on fresh grants.
   - Reuse the project's existing library or engine if it can express the
     matrix. Do not add a second one.
4. **Make roles data and check permissions.** Code asks
   `authorize(actor, "invoice:approve", invoice)`, never
   `actor.role == "admin"`. Permissions are constants in code; the mapping from
   roles to permissions, and role assignments, are data (database or
   configuration), so a new role needs no code change. Guard that data too:
   nobody grants a permission they do not hold, edits their own role, or
   removes the last owner of a tenant.
5. **Build one policy layer and route every decision through it.**
   - One module exposes `authorize(actor, action, resource)` for single objects
     and `scope(actor, action, query)` for lists. Every entry point from step 1
     calls it.
   - Deny by default: an unknown action, role, or resource type is denied, and
     a missing rule is a deny, never an exception that falls through to allow.
   - Filter lists inside the query, not after fetching, so pagination, counts,
     and totals do not leak. Framework object checks often skip lists (Django
     REST framework does not apply `has_object_permission` to list views), so
     scope the queryset explicitly.
   - Add a guard that no request finishes without a decision: an after-action
     check (for example Pundit's `verify_authorized`) or a route-inventory test
     that fails for any route that is neither on an explicit public allowlist
     nor declares a permission.
   - For resources in another tenant, return 404 rather than 403 when the API
     contract hides existence.
6. **Check objects, not just logins.**
   - Derive the actor and tenant on the server from the authenticated session
     or token. A tenant ID in a path, body, or header (`X-Tenant-ID`) is a
     request to validate against the actor's memberships, not a fact.
   - Load by ID within the tenant (`WHERE id = $1 AND tenant_id = $2`), then
     authorize the action. For nested resources, confirm the child belongs to
     a parent the caller can access.
   - Authorize every ID in a bulk operation, not only the first.
   - Never accept `tenant_id`, `owner_id`, `role`, or permission fields from
     client input (mass assignment); set them on the server.
   - GraphQL: authorize in resolvers or the schema's auth layer, including
     nested fields, and include the tenant in batch-loader keys.
   - Search and retrieval filter by tenant and permission at query time, never
     after retrieval (the `build-retrieval` skill). Cache keys include the
     tenant and any permission-relevant attributes (the `add-caching` skill).
   - Exports, reports, and signed download URLs use the same scope and expire.
7. **Scope tenants in the data layer as well.** The policy layer is the primary
   control; the data layer catches the query someone forgot.
   - Route data access through repository functions or ORM scopes that require
     a tenant context, set once per request or job from the authenticated
     identity.
   - On PostgreSQL, row-level security adds strong defense in depth (example
     below). The application role must not own the tables (or the tables use
     `FORCE ROW LEVEL SECURITY`), must not be a superuser, and must lack
     `BYPASSRLS`. Set the tenant per transaction (`set_config(..., true)` or
     `SET LOCAL`), because a session-level setting leaks across pooled
     connections.
   - Background jobs carry the tenant ID and the acting principal in the
     payload, set the tenant context before any query, and handle one tenant
     per unit of work (the `background-jobs-and-queues` skill). Cross-tenant
     maintenance runs under a separate, audited role.
   - Enabling row-level security on a live table changes every query against
     it; plan the rollout with the `safe-migration` skill.
8. **Make support access and impersonation explicit.**
   - A dedicated permission held by named staff, granted per tenant or user
     for a limited time per policy, with a reason or ticket ID, and with
     customer consent where the contract requires it. The grant expires on its
     own.
   - Every action records both the real actor and the impersonated user, and
     the UI shows a visible banner throughout.
   - Block high-risk actions while impersonating: changing credentials or MFA,
     viewing secrets, payments, and granting roles.
   - Audit grants, uses, and expiry in an append-only log that support staff
     cannot edit.
9. **Keep decisions fresh and observable.** Cache permissions only with a
   bounded lifetime, and invalidate on role or membership changes. Roles
   embedded in tokens stay stale until expiry, so re-check membership on the
   server for sensitive actions. Record denials and every role, permission,
   and sharing change as audit events.
10. **Encode the matrix as tests that run in CI.** Generate cases from actor ×
    action × resource × tenant (example below), including deny rows for
    anonymous callers, the same role in another tenant, removed members,
    suspended users, expired impersonation grants, and API keys missing a
    scope. Add one integration test per non-HTTP path (job, export, search,
    admin tool) that seeds two tenants and asserts that tenant A never sees
    tenant B's data, plus a test that a query without tenant context returns no
    rows or fails.

## Worked example: policy function and matrix test (illustrative Python)

```python
# policy.py: the single decision point.
from __future__ import annotations

from dataclasses import dataclass

ACTIONS = ("invoice:read", "invoice:approve", "invoice:delete")


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str
    permissions: frozenset[str]  # resolved from role assignments stored as data


@dataclass(frozen=True)
class Invoice:
    tenant_id: str
    created_by: str
    status: str


def authorize(actor: Actor | None, action: str, invoice: Invoice) -> bool:
    """Anything not explicitly allowed is denied."""
    if actor is None or action not in ACTIONS:
        return False
    if actor.tenant_id != invoice.tenant_id or action not in actor.permissions:
        return False
    if action == "invoice:approve":
        # Separation of duties: nobody approves their own invoice.
        return invoice.status == "draft" and invoice.created_by != actor.user_id
    if action == "invoice:delete":
        return invoice.status == "draft"
    return True
```

```python
# test_policy_matrix.py: actor x action x resource x tenant, run in CI.
import pytest

from policy import ACTIONS, Actor, Invoice, authorize

ROLES = {  # mirrors the role table; policy code never names a role
    "viewer": {"invoice:read"},
    "accountant": {"invoice:read", "invoice:approve"},
    "owner": {"invoice:read", "invoice:approve", "invoice:delete"},
}


def member(user_id: str, tenant_id: str, role: str) -> Actor:
    return Actor(user_id, tenant_id, frozenset(ROLES[role]))


ACTORS = {
    "anonymous": None,
    "viewer": member("v", "t1", "viewer"),
    "accountant": member("a", "t1", "accountant"),
    "author (accountant)": member("author", "t1", "accountant"),
    "owner": member("o", "t1", "owner"),
    "owner, other tenant": member("x", "t2", "owner"),
}
RESOURCES = {
    "t1 draft": Invoice("t1", "author", "draft"),
    "t1 approved": Invoice("t1", "author", "approved"),
}
LETTERS = "rad"  # read, approve, delete; "-" marks a denied action
EXPECTED = {
    #                        t1 draft  t1 approved
    "anonymous":            ("---",    "---"),
    "viewer":               ("r--",    "r--"),
    "accountant":           ("ra-",    "r--"),
    "author (accountant)":  ("r--",    "r--"),
    "owner":                ("rad",    "r--"),
    "owner, other tenant":  ("---",    "---"),
}


def test_matrix_is_complete():
    # A new actor, resource, or action fails here until someone decides its cells.
    assert EXPECTED.keys() == ACTORS.keys()
    assert len(LETTERS) == len(ACTIONS)
    for row in EXPECTED.values():
        assert len(row) == len(RESOURCES)
        for cell in row:
            assert len(cell) == len(ACTIONS)
            assert all(c in ("-", LETTERS[i]) for i, c in enumerate(cell))


CASES = [
    (actor, resource, action, cell[i] != "-")
    for actor, row in EXPECTED.items()
    for resource, cell in zip(RESOURCES, row)
    for i, action in enumerate(ACTIONS)
]


@pytest.mark.parametrize(("actor", "resource", "action", "allowed"), CASES)
def test_who_can_do_what(actor, resource, action, allowed):
    assert authorize(ACTORS[actor], action, RESOURCES[resource]) is allowed


def test_unknown_action_is_denied():
    assert authorize(ACTORS["owner"], "invoice:export", RESOURCES["t1 draft"]) is False
```

The same matrix drives HTTP-level tests: one request per case against the real
routes, expecting 200, 403, or 404 as the contract specifies.

Row-level security as the second line of defense (PostgreSQL, illustrative):

```sql
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;  -- applies to the table owner too

CREATE POLICY invoices_tenant_isolation ON invoices
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Each request or job transaction, before any query (true = transaction-local):
SELECT set_config('app.tenant_id', $1, true);
```

With no tenant set, the comparison is against NULL: no rows are visible and
writes fail the `WITH CHECK`, so a forgotten context fails closed.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including enabling row-level security, changing database roles or grants, or
  migrating role and permission data in a shared or production database; each
  can lock users out or expose data.
- Never weaken a test, check, or threshold to make work pass. A changed matrix
  cell is a product decision; record who made it in the change.
- Hidden UI controls, unguessable IDs, and network location are not access
  controls. UI checks are for usability only; the server decides.
- Never add a "skip authorization" flag or superuser shortcut to application
  paths. Admin tools go through the same policy layer with admin permissions.
- Do not remove an existing check until the matrix covers its replacement.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The matrix tests pass, and the completeness check fails when an action has
  no expected cells.
- The route-inventory or after-action guard passes, and fails for a route
  without a declared permission.
- Two-tenant integration tests pass for every non-HTTP path in the inventory.
- With row-level security, connected as the application role: no tenant
  context returns no rows or an error; tenant A sees none of tenant B's rows;
  inserting a tenant B row under tenant A fails.
- A repository search finds no remaining role-name comparisons or UI-only
  checks, or each remaining one is justified in the report.
- Type check, lint, and the full suite pass.

## Report

- **Model:** RBAC, ABAC, or relationship-based, why, and the library or engine.
- **Entry points:** the inventory, the check each one calls, and gaps closed.
- **Tenant isolation:** policy layer, data-layer scoping or row-level security,
  and how jobs and exports set tenant context.
- **Roles and permissions:** where the mapping lives and the escalation guards.
- **Support access:** how grants are issued, limited, expired, and audited.
- **Tests:** matrix size, deny rows, non-HTTP tests, and results.
- **Not verified:** paths or environments not exercised, and why.

## Optional delegation

The `security-reviewer` subagent can run an independent pass for IDOR,
tenant-isolation, and escalation paths before merge. The `database-architect`
subagent can review tenant columns, indexes, and row-level security design;
the `migration-planner` subagent can plan enabling it on live tables; the
`test-writer` subagent can turn the matrix into HTTP-level tests. Re-check
their findings yourself. The workflow above stays complete for a single agent.
