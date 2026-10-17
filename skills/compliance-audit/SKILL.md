---
name: compliance-audit
description: "Assess code, configuration, and data flows for readiness against GDPR, SOC 2, HIPAA, or PCI DSS controls, covering the regulated-data inventory, PII in logs, encryption, access control, audit logging, and retention and erasure, with a findings register that cites control references. Use when preparing for an audit, a customer security questionnaire, or a launch that handles regulated data. A readiness assessment, not certification or legal advice; not for exploit-focused review (use the security-review skill)."
---

# Compliance Audit

Assess whether the code, configuration, and data flows in scope support the
technical controls of a compliance framework, and report the gaps with
redacted evidence. This is a **readiness assessment, not certification or
legal advice**. Say so in every report. Only an accredited auditor or assessor
can attest compliance, and many controls (policies, training, vendor contracts,
physical security) cannot be seen in a repository at all.

## When to use

- Preparing for a SOC 2 audit, a PCI DSS assessment, a HIPAA risk analysis, or
  a GDPR review, and engineering needs to know where the code stands.
- A customer security questionnaire asks how the system handles logging,
  encryption, access, retention, or deletion.
- A feature will start storing or processing personal, health, or card data.

## When not to use

- Looking for exploitable defects: use the `security-review` skill.
- Designing a new system's threat mitigations: use the `threat-modeling` skill.
- Third-party package licenses and vulnerabilities: use the `dependency-audit` skill.
- A secret is exposed right now: use the `secret-leak-response` skill.

## Inputs to gather

Discover from the repository first; ask the user about the rest.

- **Framework and version:** for example GDPR, SOC 2 (Trust Services Criteria
  and which categories are in scope), the HIPAA Security Rule, or PCI DSS
  v4.0.1 and the assessment type. If the framework is unclear, ask.
- **The framework text or control matrix** the organization uses. Ask for it;
  citations are only as good as the source you check them against.
- **Scope:** services, paths, environments, and data classes. For PCI DSS, the
  cardholder data environment and what is out of scope.
- **Evidence sources:** data models and migrations, logging and telemetry
  configuration, auth and session code, infrastructure definitions, retention
  jobs, existing compliance docs and policies (data classification, retention
  schedule, incident response).
- **Live access**, if any: read-only replicas or exported configuration, and
  the user's approval to query them.
- **Where to save the report**, following the project's conventions.

## Workflow

1. **Fix the scope in writing.** Record the frameworks, versions, services,
   paths, and data classes, so every finding is attributable.
2. **Build the regulated-data inventory.** Map each regulated field (from
   schemas, ORM models, and API types) to its entry points (handlers,
   consumers, importers), stores (tables, object storage, caches, search
   indexes, backups), and egress (responses, webhooks, exports, analytics,
   third-party processors). Mark uncontrolled copies (debug dumps, local
   caches, analytics events) as candidate findings.
3. **Check logs, telemetry, and error traces.** Search log and telemetry call
   sites for the inventory's field names and for whole request or model
   objects passed to loggers. Confirm redaction helpers are used and cannot be
   bypassed by interpolating a raw object. Check error handlers for request
   dumps and stack traces in responses.
4. **Check encryption and key management.**
   - In transit: TLS 1.2 or later on every channel carrying regulated data,
     TLS 1.3 preferred; TLS 1.0 and 1.1 disabled; certificate verification on.
   - At rest: databases, backups, object stores, and queues holding regulated
     data use strong encryption (for example AES-256 through the platform's
     managed encryption).
   - Keys come from a KMS or secret manager, rotate per policy, and never
     appear in the repository or plaintext configuration.
5. **Check access control, tenancy, and sessions.** Least privilege for
   service accounts and roles; authorization enforced server-side; tenant
   isolation on every read and write path; MFA where the framework requires it;
   session timeout, token lifetime, and revocation; break-glass and admin paths
   that are authenticated, authorized, and logged.
6. **Check audit logging.** Security-relevant events (login, permission
   change, data export, admin action, access to regulated records) produce
   records with actor, action, target, timestamp, outcome, and source. Records
   are append-only or tamper-evident and retained for the required window. Where
   read-only access is approved, sample real events against the audit store to
   measure completeness instead of trusting the instrumentation.
7. **Check retention and erasure.** Retention jobs or lifecycle rules actually
   run, not just exist in a policy. Erasure reaches every store in the
   inventory, including search indexes, caches, analytics, and processors. If
   backups are not edited, document when they expire and how restored data is
   purged again. Compare the path end to end against the organization's
   deadline (GDPR Art. 12(3) sets one month to respond to a request, extendable
   in some cases).
8. **Write the findings register.** Re-read each finding at its `path:line`.
   For each: ID, severity, confidence, control reference, location, redacted
   evidence, impact, remediation direction, and a suggested owner. State what
   was not verified.

## Citing control references

Cite at the level you can verify. Check every control ID against the framework
text you have. If you cannot, cite the article or requirement number only and
mark it "reference not verified". Never invent sub-numbers. Starting points:

- **GDPR:** Art. 5(1)(c) data minimisation, 5(1)(e) storage limitation,
  5(1)(f) integrity and confidentiality; Art. 17 erasure; Art. 25 data
  protection by design and by default; Art. 30 records of processing; Art. 32
  security of processing; Art. 33 breach notification.
- **SOC 2 Trust Services Criteria:** CC6 logical and physical access controls
  (for example CC6.1 logical access, CC6.7 restricting transmission of
  information); CC7 system operations, including monitoring and incident
  detection (for example CC7.2); CC8.1 change management; C1 confidentiality,
  including disposal. Auditors map evidence to the organization's own
  controls, so cite those when the user provides them.
- **HIPAA Security Rule, 45 CFR 164.312 technical safeguards:** (a)(1) access
  control, (b) audit controls, (c)(1) integrity, (d) person or entity
  authentication, (e)(1) transmission security. Some implementation
  specifications are "addressable" rather than "required"; check the current
  rule text, since HHS has proposed changes to the Security Rule.
- **PCI DSS v4.0.1:** Requirement 3 (protect stored account data; for example
  3.5.1 renders PAN unreadable wherever it is stored, including logs);
  Requirement 4 (strong cryptography in transmission, 4.2.1); Requirement 7
  (access by need to know); Requirement 8 (identification and authentication,
  including MFA); Requirement 10 (logging and monitoring; 10.5.1 sets audit log
  retention).

## Reference snippets

Illustrative searches for step 3; replace the field names with the inventory's
and adapt the logger names to the stack:

```bash
rg -n -i '(log|logger|console)\.(debug|info|warn|error)\(.*\b(email|phone|ssn|dob|card_?number|diagnosis)\b' src/
rg -n -i '(log|logger)\.\w+\(.*\b(req|request)\.(body|headers)\b' src/
```

An illustrative redaction regression test (pytest; the module is hypothetical).
It inspects record attributes too, so values passed through `extra=` are caught:

```python
import logging
import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def test_logs_exclude_regulated_identifiers(caplog):
    from billing.invoice_service import issue_invoice  # hypothetical module

    with caplog.at_level(logging.DEBUG):
        issue_invoice(customer_email="alice@example.com", ssn="123-45-6789")

    rendered = "\n".join(
        f"{record.getMessage()} {vars(record)}" for record in caplog.records
    )
    assert not EMAIL.search(rendered), "email reached log output"
    assert not SSN.search(rendered), "SSN reached log output"
```

An illustrative audit-log completeness query for a read-only replica (table
names are hypothetical); a non-zero count is a completeness gap:

```sql
SELECT COUNT(*) AS missing_or_incomplete
FROM security_event e
LEFT JOIN audit_log a ON a.event_id = e.id
WHERE e.occurred_at >= NOW() - INTERVAL '24 hours'
  AND (a.id IS NULL OR a.actor_id IS NULL OR a.source_ip IS NULL);
```

An illustrative register entry:

```yaml
- id: F-001
  severity: high
  confidence: high
  controls: ["GDPR Art. 5(1)(c)", "GDPR Art. 32", "SOC 2 CC6 (map to org control)"]
  location: src/billing/invoiceService.ts:87
  evidence: "logger.info(`invoice issued for ${customer.email}`), no redact() call"
  impact: Customer email addresses are written to plaintext application logs.
  remediation: Log the internal customer ID, or pass the value through redact().
  suggested_owner: billing team
```

## Guardrails

- State that the result is a readiness assessment, not certification,
  attestation, or legal advice. Route legal interpretation to the user's
  counsel or assessor.
- Stay read-only. Do not change authorization rules, audit-log settings,
  retention jobs, or production configuration; remediation is a separate,
  approved change.
- Revert or delete only files you created in this session, and say so. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions.
  Query production data only through approved read-only replicas or exports,
  with read-only credentials.
- Redact every excerpt before it is written anywhere. Raw regulated values never
  enter the report, evidence files, or the conversation.
- Store evidence and registers where access is restricted; they describe gaps
  and must not become an attack map. Do not commit them to a public location.
- Never relax severity, scope, or control mappings mid-audit to make the result
  look better, and never weaken a test or check.
- Never invent control IDs, deadlines, or retention periods. Use the framework
  text and the organization's policy, or mark the item unverified.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Every finding was re-read at its `path:line`, and every control reference was
  checked against the framework text or marked unverified.
- Redaction and audit-logging tests, if the project has or adds them, ran
  through the project's test runner with their results recorded.
- Evidence files and the report were searched with the same regulated-data
  patterns and contain no raw values.
- Any live query ran against an approved read-only target, and its result is
  recorded with the time it ran.

## Report

- **Statement:** readiness assessment only; not certification or legal advice.
- **Scope:** frameworks and versions, services, paths, data classes, exclusions.
- **Regulated-data inventory:** fields mapped to entry points, stores, egress.
- **Findings register:** by severity, with confidence, control references,
  `path:line`, redacted evidence, impact, remediation, and suggested owner.
- **Control coverage:** areas checked (logging, encryption, access, audit
  logging, retention and erasure) and what each showed.
- **Not verified:** runtime behavior, third-party processors, organizational
  and physical controls, unverified control references, and stores not reached.
- **Next actions:** remediation in priority order and evidence the auditor
  will likely request.

## Optional delegation

The `compliance-auditor` subagent can trace one framework or one service in
parallel; the `security-reviewer` subagent can confirm whether a gap is also
exploitable. Re-check any delegated finding at its `path:line` before
reporting it. One agent can complete this workflow alone.
