---
name: secret-leak-response
description: "Respond to a leaked credential (API key, token, password, or private key) committed to git, pasted in logs, or shipped in a build artifact: revoke or rotate it first, size the blast radius from audit logs, remove it from the current tree, rewrite history only with approval, and add prevention. Use when a secret was exposed or a scanner, push protection, or provider alert flags one. For active abuse, also use the incident-triage skill."
---

# Secret Leak Response

Contain a leaked credential and stop it from recurring. The stance is **rotate
first, clean up second**: a secret is compromised from the moment it was pushed,
published, or logged, and rewriting history does not un-leak it.

## When to use

- A credential was committed (pushed or not), pasted into a log, ticket, chat, or
  CI output, or baked into an artifact, image, or package. This includes a
  `.env`, key, or config file with real values found in the repository.
- A secret scanner, push protection, or a provider reports an exposed credential.

## When not to use

- Evidence of active misuse (unexpected resources, data access, or charges): do
  the containment step here, and use the `incident-triage` skill to coordinate
  the wider response.
- General review of code for security flaws: use the `security-review` skill.
- A placeholder or test fixture that never worked anywhere: confirm with the
  owner that it is not real, then clean it up without rotation.

## Inputs to gather

Never ask for, print, or repeat the secret value. Refer to it by type, last four
characters, and location.

- Credential type and issuer (cloud access key, database password, OAuth client
  secret, signing key, webhook secret, personal access token) and its owner.
- Every exposure location (`path:line`, commits, branches, tags, CI logs,
  artifacts, images, packages) and whether each is public or private.
- When it was first exposed and detected. A push or publish can come later than
  the commit date; use the exposure time when known.
- What it grants: scopes, roles, environments, and resources.
- Who can rotate it, every consumer (services, CI, other teams), and how a new
  value is deployed.
- The project's secret management (secret manager, CI secrets, environment
  variables) and existing scanning setup.

## Workflow

1. **Contain: revoke or rotate first.** Identify the credential type and owner,
   then get it revoked or rotated through the provider before any cleanup. This
   is a production action: confirm with the owner, but treat it as urgent and
   never let cleanup or a code fix delay it.
   - **Rotate without downtime** when there is no sign of misuse: issue a new
     credential, deploy it to every consumer, confirm they use it, then revoke
     the old one.
   - **Revoke immediately** when misuse is suspected, even if it causes an
     outage. Recommend this plainly; the owner decides.
   - If you cannot revoke it yourself, give the owner the provider's exact steps
     and track revocation as the blocking item.
2. **Assess the blast radius.**
   - Access: read the credential's scopes, attached policies, or role, and list
     the environments and data it reaches.
   - Exposure window: first exposure to revocation. Scanners harvest public
     pushes quickly; treat any public exposure as already collected.
   - Misuse: review provider audit logs over the window, for example AWS
     CloudTrail and IAM last-used data, the GitHub organization audit log, cloud
     activity logs, database connection logs, and billing anomalies. Query this
     metadata with your own credentials; never authenticate with the leaked one.
   - Copies: check other branches and tags, forks, open pull requests, CI logs,
     caches, container images, published packages, and pasted tickets or chats.
     Scan the full history for other secrets at the same time, for example with
     gitleaks and its `--redact` option (subcommands differ between versions;
     check `gitleaks --help`).
   - If you find evidence of misuse, use the `incident-triage` skill.
3. **Remove it from the current tree.** Replace the literal with a reference to
   the secret manager, a CI secret, or an environment variable. Keep a
   `.env.example` with variable names and dummy values, and add real env and key
   files to `.gitignore`. Commit the removal normally. This stops further spread,
   but the value stays in history and in every clone, which is why step 1 comes
   first. Then handle copies outside git: delete affected CI logs, rebuild and
   replace artifacts and images (a file deleted in a later image layer still
   exists in the earlier one), and deprecate or replace published packages
   (registry unpublish rules are limited; rotation is still required). Those
   deletions are destructive or outward-facing; ask first.
4. **Rewrite history only with approval.** Once the credential is revoked,
   rewriting is optional. It is worth it when the value cannot be rotated soon,
   when the file also holds other sensitive data, or when policy requires it.
   Explain the cost before asking:
   - Every later commit SHA changes; open pull requests, signatures, and links
     to commits break.
   - It needs coordinated force-pushes of all affected branches and tags,
     temporarily relaxed branch protection, and every collaborator re-cloning.
     An old clone pushed back reintroduces the secret.
   - Forks, existing clones, and hosting caches keep the old commits. On GitHub,
     removing cached views and pull request references requires GitHub Support.
5. **Prevent recurrence.** Propose these and ask before changing shared hooks,
   CI, or repository settings:
   - Pre-commit secret scanning, for example gitleaks through the pre-commit
     framework (snippet below).
   - The host's secret scanning and push protection, plus a CI secret scan so a
     skipped local hook is still caught.
   - `.gitignore` entries for `.env`, `*.pem`, key files, and local configuration.
   - Secrets loaded from a secret manager or CI secrets, masked in CI logs, and
     never printed in config dumps or error messages.
   - Short-lived credentials where the platform supports them, for example OIDC
     federation from CI to the cloud instead of stored keys.
6. **Record an incident note** (template under Report). Ask where it belongs; a
   public repository is often the wrong place. It never contains the secret.

## Reference commands

Illustrative. Adapt names and paths; run each separately.

```bash
# Where the file or variable appears in history (search names, never the value).
git log --all --format='%h %ad %an %s' --date=iso -- config/settings.py
git log --all -S 'PAYMENTS_API_KEY' --oneline
git branch -a --contains 3f2c1aa
git tag --contains 3f2c1aa

# AWS metadata, queried with your own credentials. An access key ID is an
# identifier, not the secret. Event history covers recent management events
# per region; an organization trail may hold more.
aws iam get-access-key-last-used --access-key-id KEY_ID
aws cloudtrail lookup-events --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=KEY_ID
```

History rewrite with git filter-repo, only after the user approves. Follow your
host's current guide for removing sensitive data, and check
`git filter-repo --help`; recent versions add options for this case.

```bash
git clone --mirror https://github.com/ORG/REPO.git repo-cleanup.git
cd repo-cleanup.git
git filter-repo --invert-paths --path config/credentials.json   # requires approval
git remote -v                                                   # filter-repo may remove origin; re-add it deliberately
git push --force --mirror origin                                # requires approval
```

To replace a value rather than delete a file, `--replace-text` reads literals
from a file that the user writes outside any repository and deletes afterwards.
BFG Repo-Cleaner is an alternative; by default it leaves the latest commit
untouched, so finish step 3 first. On GitHub, rejected `refs/pull/*` updates
during the push are expected. Afterwards, rescan the rewritten history and ask
collaborators to re-clone rather than pull.

```yaml
# Pre-commit hook in .pre-commit-config.yaml (pin rev to a released gitleaks tag)
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: vX.Y.Z
    hooks:
      - id: gitleaks
```

## Guardrails

- Never paste, echo, or log the secret value in chat, tickets, commits, reports,
  or command lines. Refer to it by type, last four characters, and location. Use
  a scanner's redaction option rather than printing the file or commit.
- Never test the leaked credential against production or any live system to see
  whether it works. Use the provider's metadata, queried with your own
  credentials.
- History rewrites, force-pushes, branch-protection changes, and deleting logs,
  artifacts, images, or package versions need explicit approval. Mark such
  commands `# requires approval`.
- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Do not call the leak resolved because the file was deleted or history was
  rewritten. It is contained only when the credential is revoked.
- Never weaken or disable secret scanning to make a check pass. Allowlist only
  verified false positives, one at a time.

## Verification

Run each check separately and report its real result; never chain alternatives
with `||`.

- The old credential shows as revoked, deleted, or inactive in the provider's
  console or API; do not assume it.
- Every consumer works with the new credential (health checks, a CI run).
- A secret scan of the working tree finds no copy, and a search for the file or
  variable name finds only the new reference.
- If history was rewritten, a scan of the full rewritten history finds no copy,
  and every branch and tag was pushed.
- New prevention works: the hook or CI scan blocks a deliberately fake value.

## Report

- **Credential:** type, issuer, owner, last four characters, and locations
  (`path:line`, commits, artifacts). Never the value.
- **Timeline:** first exposure, detection, and revocation; the exposure window.
- **Containment:** revoked or rotated, by whom, and consumer cutover status.
- **Blast radius:** access granted, logs reviewed and their time range, and
  evidence of misuse, or "none found in the logs reviewed".
- **Cleanup:** current-tree fix, copies removed outside git, and history rewrite
  done or declined with the reason.
- **Prevention:** hooks, scanning, ignore rules, and process changes, applied or
  proposed.
- **Not verified:** checks that could not run, open items, and their owners.

Incident note:

```markdown
# Incident: exposed CREDENTIAL_TYPE ending LAST4

- Owner:
- Exposure: where, public or private, first exposed, detected, revoked
- Access: scopes and resources reachable
- Misuse review: logs checked, time range, findings
- Actions: rotation, cleanup, history rewrite (yes or no, and why)
- Prevention: changes made and proposed
- Follow-ups: owner and due date for each
```

## Optional delegation

The `security-reviewer` subagent can assess what the credential could reach,
review the remediation diff, and look for other hard-coded secrets nearby. For
active abuse, the `incident-commander` subagent can coordinate while you
contain. One agent can complete this workflow alone.
