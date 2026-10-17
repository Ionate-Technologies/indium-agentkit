---
name: threat-modeling
description: "Build a threat model for a planned feature, service, or architecture change by mapping assets, data flows, and trust boundaries, enumerating STRIDE threats per boundary, scoring likelihood times impact, and assigning testable mitigations and residual-risk owners. Use before implementing or redesigning anything that handles sensitive data, authentication, payments, external integrations, or LLM tools. Not for reviewing code that already exists (use the security-review skill)."
---

# Threat Modeling

Produce a threat model before code is written, so that mitigations become
requirements instead of patches. The stance is **evidence-backed and
pre-implementation**: every threat rests on a real component, data flow, and
attacker, and every serious threat leaves with a mitigation, a planned test,
and an owner for what remains.

## When to use

- A new feature or service will handle personal, payment, health, or
  credential data, or will expose a new public endpoint.
- An architecture change adds a trust boundary: a new third-party API, queue,
  data store, tenant model, admin surface, or LLM tool.
- A design review, security sign-off, or customer questionnaire needs a
  documented model.
- An existing model is stale because the system changed.

## When not to use

- The code already exists and needs checking for defects: use the
  `security-review` skill.
- Readiness against a compliance framework: use the `compliance-audit` skill.
- Cloud and infrastructure posture: use the `infrastructure-review` skill.
- Choosing and implementing ciphers, signatures, or TLS settings: use the
  `cryptographic-protocol-implementation` skill.
- Implementing the authentication and authorization the model calls for: use
  the `implement-authentication` and `access-control-design` skills.

## Inputs to gather

Discover from the repository and the request; ask only about what remains
ambiguous and would change the result.

- **Scope:** the feature, service, or change; the feature brief, plan, or
  API contract if one exists.
- **Architecture evidence:** design docs, ADRs, diagrams, API specs, auth
  model, deployment topology, and the code paths involved.
- **Existing models:** for example under `docs/security/threat-models/`. Update
  an existing model rather than creating a duplicate.
- **Data classification policy**, if the project has one.
- **Risk scale and appetite:** the project's scoring scale, the threshold that
  requires mitigation before implementation, and who may accept residual risk.
- **Save location:** the project's documentation convention for security
  artifacts.

## Workflow

1. **Recon.** Read `AGENTS.md`, the design material, and the relevant code.
   Where documentation is missing or stale, reconstruct the data flow from code
   (routes, clients, queries, queue producers and consumers). Label each
   element as documented, code-derived, or assumed. Never present an assumption
   as fact.
2. **List assets and classify data.** Assets worth attacking: records,
   credentials and sessions, money movement, admin capabilities, model and tool
   access, and the availability of the service. Classify the data on each flow
   (for example public, internal, personal, payment, health, credentials) using
   the project's policy where one exists.
3. **Draw the data flow and enumerate trust boundaries.** List processes, data
   stores, external entities, and flows. A trust boundary is any point where
   data passes between different levels of trust: browser to API, API to
   database, service to third party, job runner to queue, untrusted content
   into an LLM context. For each boundary record the channel, the
   authentication on the crossing, and the data classes carried. Every flow
   that crosses a trust level must appear; a model with no boundaries is wrong.
   A Mermaid flowchart is optional; a table is enough.
4. **Enumerate STRIDE threats per boundary.** For each boundary, ask:
   - **Spoofing:** can an attacker impersonate a user, a service, or the
     endpoint on the other side?
   - **Tampering:** can data in transit or at rest be modified (payload edits,
     row updates, queue messages, retrieved documents that steer a model)?
   - **Repudiation:** can an actor act without an audit record tying the action
     to their identity?
   - **Information disclosure:** can data leak through responses, errors, logs,
     caches, side channels, or tool calls that send data outward?
   - **Denial of service:** can resources be exhausted (unbounded payloads,
     expensive queries, retry storms, quota or token abuse)?
   - **Elevation of privilege:** can an actor gain control they should not
     have (missing object-level checks, role confusion, confused deputies, a
     model invoking a privileged tool on injected instructions)?

   Record only threats with evidence: a real crossing, a real data class, and a
   plausible attacker. If a boundary has no credible threat in a category,
   record "assessed, none credible" with the reason, so coverage is visible.
5. **Score.** Unless the project defines a scale, rate likelihood and impact
   each from 1 to 5 and multiply them, giving a risk from 1 to 25.
   - Likelihood: 1 needs rare insider access or chained exploits; 3 needs an
     authenticated user or a known technique; 5 is trivial for an anonymous
     attacker.
   - Impact: 1 is negligible; 3 is limited data exposure or degraded service
     for some users; 5 is broad data compromise, financial loss, or full outage.
   - Thresholds follow the project's risk appetite; for example, 15 or more
     must be mitigated before implementation, 8 to 14 must be mitigated or
     formally accepted, and lower scores are recorded.
   - DREAD (the average of five 1-to-5 factors) is optional and subjective; use
     it only if the project already does. Never mix scales within one model.
6. **Design mitigations.** For each threat at or above the threshold, name a
   concrete control mapped to a component and boundary: request signing,
   mTLS, object-level authorization, parameterized queries, rate limits,
   schema validation, audit logging, token rotation, egress allowlists, human
   confirmation for consequential tool calls. Prefer controls that fail closed.
   "Add more security" is not a control. Give each mitigation a planned
   verification test that follows the project's test layout.
7. **Assess residual risk.** For each threat, state what remains after
   mitigation and why it is acceptable. Residual risk needs a named owner (a
   role or person the user identifies). Do not accept risk on anyone's behalf;
   list unowned items as open questions.
8. **Write the handoff document** using the headings in Report. Save it where
   the project keeps security documents, for example
   `docs/security/threat-models/checkout-flow.md`. Do not save it over a
   template file. If a model already exists at that path, update it and keep
   its history; ask before replacing it wholesale. Reference it from the
   feature brief or plan it gates.

## Worked example: threat inventory excerpt

Illustrative rows for a checkout flow (browser to checkout API to order
database to payments provider), scored likelihood (L) times impact (I).

```markdown
| ID  | Boundary          | STRIDE      | Threat and evidence                                          | L | I | Risk | Mitigation (component)                    | Planned test                              |
|-----|-------------------|-------------|--------------------------------------------------------------|---|---|------|-------------------------------------------|-------------------------------------------|
| T-1 | TB-1 browser->API | Spoofing    | Stolen session token confirms orders as another user;        | 3 | 4 | 12   | Rotate token at checkout start, bind it   | Pre-rotation token rejected at confirm    |
|     |                   |             | 24-hour tokens, no rotation (src/auth/session.ts, code)      |   |   |      | to the cart (checkout-api)                |                                           |
| T-2 | TB-2 API->DB      | Tampering   | Order notes concatenated into a raw UPDATE; can alter other  | 4 | 5 | 20   | Parameterize; add tenant predicate to     | Metacharacter payload changes zero rows   |
|     |                   |             | tenants' rows (src/repos/orders.ts, code-derived)            |   |   |      | every order mutation (checkout-api)       |                                           |
| T-3 | TB-3 API->provider| Repudiation | Disputed charge cannot be tied to a user action; no audit    | 3 | 3 | 9    | Append-only audit row (actor, cart,       | Audit row exists for every charge         |
|     |                   |             | event links confirmation to the provider charge ID           |   |   |      | charge ID) before the provider call       |                                           |
| T-4 | TB-1 browser->API | DoS         | Unbounded confirm attempts exhaust provider quota; no rate   | 4 | 3 | 12   | Per-user and per-IP rate limit, circuit   | Requests over the limit return 429;       |
|     |                   |             | limit on POST /checkout/confirm                              |   |   |      | breaker on provider errors                | breaker opens in test                     |

Residual: T-1 token theft through XSS remains until the CSP work lands.
Owner: security lead (to be confirmed by the user). T-4 distributed abuse
above per-IP limits needs an edge rule; owner: platform team.
```

## Guardrails

- Revert or delete only files you created in this session, and say so. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
- Never weaken a test, check, or threshold to make work pass, and never lower a
  score to avoid a required mitigation.
- Write only the threat-model document (and the plan or brief reference, if
  asked). Do not change system code while modeling.
- Do not run penetration tests or exploits against live systems; reason from
  architecture and code, and validate through scoped tests later.
- Keep secrets, tokens, real payloads, and customer data out of the model.
  Name secret-store entries with placeholders.
- Never claim all threats are eliminated. A model produced after
  implementation is a review: say so and use the `security-review` skill.

## Verification

- Every trust boundary has at least one assessment, including "assessed, none
  credible" entries with reasons.
- Every threat at or above the threshold has a mitigation mapped to a
  component and a planned test.
- Every residual risk has an owner or appears under open questions.
- Every evidence reference resolves to a real file or document, and
  code-derived or assumed elements are labeled.
- The document contains every heading in Report. If the project lints
  Markdown, run its command on the file and report the result.
- After implementation, the mapped tests exist and pass with the project's
  test command before the model is marked closed.

## Report

Return the saved path, the number of boundaries and threats, the top risks
with scores, unowned residual risks, open questions, and what was not
verified (for example, assumed components or undocumented deployment details).

<!-- handoff: threat-model -->
```markdown
# Threat model: <system or feature name>

## Scope and system overview
In-scope components, data stores, external entities, and flows; evidence
sources (documents read, code paths reconstructed); assumptions.

## Trust boundaries and assets
| Boundary | From | To | Channel | Auth on crossing | Data classes | Assets |

## STRIDE threat inventory
| ID | Boundary | STRIDE | Threat and evidence | Likelihood | Impact | Risk | Mitigation (component) | Planned test |
Scale used and the mitigation threshold.

## Residual risk assessment
| Threat | Residual risk | Rationale | Owner | Follow-up |

## Open questions
Decisions needed from security, product, or operations before implementation.

## Handoff
**Changed contract:** Security requirements this model adds to the feature.
**Files / systems affected:** Components and boundaries that need mitigations.
**Evidence and tests:** Evidence sources and the planned tests per mitigation.
**Risks / rollback:** Residual risks, accepted risks, and their owners.
**What the next agent needs:** Mitigation tasks in priority order.
```

## Optional delegation

The `security-reviewer` subagent can check the model against the code for
missed boundaries or flows and challenge the scores; the `plan-reviewer`
subagent can confirm that the implementation plan includes every required
mitigation. Re-check their findings before changing the model. One agent can
complete this workflow alone.
