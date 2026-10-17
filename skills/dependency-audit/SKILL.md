---
name: dependency-audit
description: "Audit a project's dependencies for known vulnerabilities, license risk, staleness, unused packages, and version-constraint problems using lockfiles and read-only scanners such as npm audit, pip-audit, osv-scanner, govulncheck, and cargo audit, then write a dependency-audit report. Use when asked to check dependencies, before a release, when an advisory lands, or when a customer asks for an SBOM. Audit only; not for performing upgrades (use the upgrade-dependencies skill)."
---

# Dependency Audit

Find out what the project depends on, what is vulnerable, what is risky to
ship, and what to do about it, without changing the dependency tree. The
stance is **audit only, sourced findings**: scanners run in read-only or
lockfile-only modes, raw output goes to a temporary directory, and every
severity in the report names its source or says `unknown`.

## When to use

- A request to check dependencies for vulnerabilities, licenses, or health.
- Before a release, after a new advisory, or when a dependency is added.
- A customer or auditor asks for an SBOM or a dependency risk summary.

## When not to use

- Performing upgrades or major-version migrations: use the
  `upgrade-dependencies` skill.
- Reviewing the project's own code for vulnerabilities: use the
  `security-review` skill.
- A leaked registry token or credential: use the `secret-leak-response` skill.

## Inputs to gather

Discover from the repository first; ask only about what remains ambiguous.

- **Ecosystems:** every manifest and lockfile pair, including workspaces and
  nested packages (`package.json` with `package-lock.json`, `pnpm-lock.yaml`,
  or `yarn.lock`; `pyproject.toml` or `requirements*.txt` with `poetry.lock`
  or `uv.lock`; `Cargo.lock`; `go.mod` and `go.sum`; `Gemfile.lock`; and so on).
- **Policies:** license allowlists, update rules in `AGENTS.md`, Dependabot or
  Renovate configuration, and any vulnerability gate (for example "no
  unresolved critical or high in production dependencies").
- **Distribution model:** hosted service, distributed binary, mobile app, or
  published library. License obligations depend on it.
- **Scope:** production only or all dependencies, and whether transitive
  dependencies count.
- **Tools available:** which scanners are installed. Do not install tools
  without asking.
- **Network and privacy:** most scanners send package names and versions to an
  advisory service. Ask before running them if private package names are
  sensitive.
- **Where to save the report**, following the project's conventions.

## Workflow

1. **Inventory.** List each manifest and lockfile pair with lockfile presence
   and age. A manifest without a lockfile, or a lockfile that no longer
   satisfies its manifest, is a finding.
2. **Choose scanners per ecosystem.** Prefer the project's own audit script.
   Otherwise, as available:
   - **Any ecosystem:** `osv-scanner` reads lockfiles across ecosystems without
     installing anything. The command shape differs between major versions
     (`osv-scanner scan source -r .` on v2, `osv-scanner -r .` on v1); check
     `osv-scanner --help`.
   - **npm, pnpm, Yarn:** `npm audit --json --package-lock-only`,
     `pnpm audit --json`, `yarn audit --json` (Yarn 1), or
     `yarn npm audit --all --recursive --json` (Yarn 2 and later).
   - **Python:** `pip-audit --format json` audits the active environment.
     For a fully pinned requirements file, add
     `-r requirements.txt --no-deps --disable-pip` so it does not install
     anything to resolve dependencies; confirm with `pip-audit --help`.
   - **Go:** `govulncheck ./...` reports which vulnerabilities your code
     actually calls (reachability), not just which modules are present.
   - **Rust:** `cargo audit --json`, or `cargo deny check` if the project
     configures it (it also covers licenses and banned crates).
   - **Ruby:** `bundle-audit check --update`.
   - **.NET:** `dotnet list package --vulnerable --include-transitive`.
   - **SBOM:** `syft dir:. -o cyclonedx-json` or the ecosystem's CycloneDX
     generator (for example `cyclonedx-npm`, `cyclonedx-py`, or
     `cargo cyclonedx`). An SBOM can then be scanned with a tool such as
     `grype`.
3. **Run the scans with output outside the repository.** Record each command,
   tool version, advisory database date, and exit code. Most scanners exit
   non-zero when they find vulnerabilities; that is a result, not a tool
   failure. Treat missing or unparseable output as a failed scan and say so.
   Illustrative, for a POSIX shell (on Windows, create the directory under
   `[System.IO.Path]::GetTempPath()` instead):

   ```bash
   # Run only the lines for ecosystems the project uses.
   OUT="$(mktemp -d)"
   npm audit --json --package-lock-only > "$OUT/npm-audit.json"
   pip-audit --format json > "$OUT/pip-audit.json"   # in the project's virtualenv
   osv-scanner scan source --format json -r . > "$OUT/osv.json"
   govulncheck ./... > "$OUT/govulncheck.txt"
   syft dir:. -o cyclonedx-json > "$OUT/sbom.cdx.json"
   echo "scan output in $OUT"
   ```
4. **Normalize and source the severity.** Build one register with: ecosystem,
   package, installed version (read from the lockfile, not the advisory's
   affected range), advisory ID and aliases (CVE, GHSA, PYSEC, RUSTSEC, GO),
   severity and its source, fixed versions, direct or transitive (with the
   parent chain), production or development, reachability if known, and the
   tool that reported it. Deduplicate across tools by alias.
   - npm audit: take severity from the advisory objects in `via` and map
     `moderate` to `medium`. String entries in `via` point to another
     vulnerable package; do not count them twice.
   - pip-audit JSON does not carry a reliable severity. Mark it `unknown`, or
     look up the ID or alias in OSV (osv.dev) or the GitHub Advisory Database,
     with approval for the network call, and record where it came from.
   - The Go vulnerability database does not assign severity; mark `unknown` or
     look up the CVE or GHSA alias. Keep govulncheck's called versus
     not-called distinction.
   - RustSec informational advisories (unmaintained, unsound, yanked) have no
     severity; report them under staleness and maintenance.
   - Where a CVSS base score exists, map it to bands: 0.1 to 3.9 `low`, 4.0 to
     6.9 `medium`, 7.0 to 8.9 `high`, 9.0 to 10.0 `critical`.
5. **Add context without rewriting severity.** Keep the advisory severity and
   add a priority based on reachability, production use, and exposure. A
   reachable `medium` in an internet-facing service can outrank an unreachable
   `high` in a development tool; say why.
6. **Analyze licenses.** Take licenses from the SBOM, package metadata, or a
   configured tool (for example `cargo deny check licenses`). Compare with the
   policy and distribution model:
   - Strong copyleft (GPL, AGPL, which also applies to network use, and SSPL):
     blocking or review, per policy.
   - Weak copyleft (LGPL, MPL-2.0, EPL-2.0): review linking and modification
     obligations.
   - Permissive (MIT, BSD, Apache-2.0, ISC): usually clear; note attribution
     and NOTICE obligations.
   - Unknown, missing, custom, or conflicting declarations: review.

   This is a risk summary, not legal advice; route decisions to the people who
   own licensing.
7. **Assess staleness and maintenance.** For direct dependencies at least:
   current versus latest version, last release date, deprecation notices,
   yanked versions, archived repositories, and single-maintainer or
   unanswered-security-issue signals. Use the project's threshold; a mature
   library with no recent release is a prompt to look, not automatically a
   finding.
8. **Find unused, duplicated, and loosely constrained dependencies.** If
   installed, use tools such as `knip` or `depcheck` (JavaScript), `deptry`
   (Python), or `cargo machete` (Rust), and `npm ls <package>` or
   `cargo tree -d` for duplicates. Flag broad ranges (`*`, `latest`, open
   `>=`), Git or URL dependencies without a pinned commit, and hard pins that
   block security patches. Confirm each candidate by reading imports and build
   configuration before reporting it.
9. **Recommend.** For each vulnerable package: the fixed version, the upgrade
   path (direct bump, parent bump, or an override such as npm `overrides`,
   Yarn `resolutions`, or `pnpm.overrides`), whether it is a major-version
   change, and a mitigation when no fix exists (disable the feature, constrain
   input, or replace the package). Order by priority. Implementation goes to
   the `upgrade-dependencies` skill once the user approves.
10. **Write the report** using the headings in Report. Save it where the
    project keeps such documents (for example
    `docs/security/dependency-audit-YYYY-MM-DD.md`), or return it in the
    conversation if the user does not want a file. Leave raw scan output in
    the temporary directory unless the user asks to keep it.

## Worked example: normalized findings

Illustrative rows with placeholder packages and advisory IDs.

```markdown
| Severity (source)          | Package         | Eco.  | Installed | Fixed  | Advisory            | Path                      | Reachable        | Remediation                                      |
|----------------------------|-----------------|-------|-----------|--------|---------------------|---------------------------|------------------|--------------------------------------------------|
| high (GHSA)                | example-parser  | npm   | 2.3.1     | 2.3.4  | GHSA-xxxx-xxxx-xxxx | via build-tool 5.1.0, dev | n/a (build only) | Bump build-tool to a release using 2.3.4         |
| unknown (pip-audit, OSV    | example-http    | PyPI  | 1.8.0     | 1.8.2  | PYSEC-XXXX-NN       | direct, production        | unknown          | Pin 1.8.2 after reading its changelog            |
| lookup not approved)       |                 |       |           |        |                     |                           |                  |                                                  |
| medium (CVE alias, NVD)    | example-yaml    | Go    | v0.9.0    | v0.9.3 | GO-XXXX-NNNN        | direct, production        | called           | Bump; priority raised because the code calls it  |
| none (RustSec unmaintained)| example-tls-sys | Rust  | 0.4.2     | none   | RUSTSEC-XXXX-NNNN   | via http-stack 1.2        | n/a              | Track the parent's migration; plan a replacement |
```

## Guardrails

- Audit only. Never install, upgrade, remove, or deduplicate dependencies, and
  never regenerate a lockfile, without explicit approval.
- Never run package install scripts during an audit (`npm install`,
  `pip install`, `bundle install`, or building source distributions). Prefer
  lockfile-only modes. If a scanner can only resolve by installing, ask first,
  and use a throwaway environment with scripts disabled (for example
  `--ignore-scripts`).
- Write scan output to a temporary directory outside the repository. The only
  file written in the repository is the report, where the user wants it.
- Revert or delete only files you created in this session, and say so. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including sending private package names to external services.
- Never weaken a test, check, or policy threshold to make the audit pass, and
  never assign a severity you could not source.
- Treat registry tokens and advisory-service credentials as secrets: refer to
  them by environment variable name and keep them out of reports and logs.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- `git status --porcelain` shows no changes to manifests or lockfiles and no
  new files in the repository other than the report.
- Each finding's installed version comes from the lockfile and falls inside
  the advisory's affected range.
- Each severity names its source or is `unknown`.
- Finding counts reconcile with the raw scanner output after deduplication.
- Each scan's command, tool version, database date, and exit code is recorded,
  and failed or skipped scans are listed.

## Report

Return the report path, the top-priority actions, and what was not covered
(ecosystems without a scanner, skipped scans, unapproved lookups).

<!-- handoff: dependency-audit-report -->
```markdown
# Dependency audit report: <project>

## Scope
Ecosystems, manifests and lockfiles, production or all dependencies, tools
with versions and database dates, and the date of the audit.

## Inventory summary
| Ecosystem | Lockfile | Direct | Transitive | Lockfile in sync |

## Vulnerability findings
| Severity (source) | Package | Installed | Fixed | Advisory | Path | Reachable | Priority |

## License analysis
| Package | License | Policy result | Notes |

## Staleness and maintenance
| Package | Current | Latest | Last release | Signal |

## Recommendations
Prioritized actions, each marked patch, minor, or major, with mitigations
where no fix exists. Unused and loosely constrained dependencies.

## Handoff
**Changed contract:** None; the audit changed no dependencies.
**Files / systems affected:** Manifests and lockfiles that the recommendations would change.
**Evidence and tests:** Scan commands, tool versions, database dates, exit codes.
**Risks / rollback:** Breaking-change risk of each recommended upgrade.
**What the next agent needs:** Approved upgrades for the upgrade-dependencies skill, plus blockers.
```

## Optional delegation

The `dependency-auditor` subagent can scan one ecosystem or workspace in
parallel; the `security-reviewer` subagent can judge whether a vulnerable code
path is reachable when no tool can tell. Re-check delegated findings against
the lockfile before reporting them. One agent can complete this workflow alone.
