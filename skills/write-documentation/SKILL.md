---
name: write-documentation
description: "Write or update project documentation from code evidence: READMEs, tutorials, how-to guides, reference pages, explanations, and architecture decision records, running each documented command or marking it unverified. Use when asked to document a feature, API, CLI, configuration, or design decision, fix stale or broken docs, or write an ADR. Not for onboarding guides (use the onboard-to-codebase skill) or AGENTS.md and CLAUDE.md files (use the init-agent-context skill)."
---

# Write Documentation

Produce documentation that is true for the code as it is today, written for one
reader and one purpose. The stance is **evidence over memory**: every fact
comes from the code, a command you ran, or a cited source, and anything
unverified is labeled as such.

## When to use

- A feature, API, CLI, configuration option, or module needs docs, or existing
  docs are stale, wrong, or broken.
- A design decision needs an architecture decision record (ADR).
- A README needs to be written or brought up to date.

## When not to use

- A guide for new contributors to set up and find their way: use the
  `onboard-to-codebase` skill.
- `AGENTS.md`, `CLAUDE.md`, or similar agent context files: use the
  `init-agent-context` skill.
- Release notes or changelog entries: use the `release-notes` skill.
- Operational procedures for incidents or maintenance: use the `write-runbook` skill.
- Designing an API contract before it exists: use the `api-design` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Reader and goal:** who reads it (new user, integrator, contributor,
  operator) and what they need to do or understand.
- **Existing docs:** location (`README.md`, `docs/`, a site generator such as
  Docusaurus, MkDocs, Sphinx, or VitePress), style guide, heading and tone
  conventions, and the ADR directory and numbering if one exists (for example
  `docs/adr/` or `docs/decisions/`).
- **Sources of truth:** public signatures and types, CLI `--help` output,
  configuration schemas and defaults, OpenAPI or GraphQL schemas, tests, and the
  changelog.
- **Docs tooling:** markdownlint or Vale configuration, link checker, doc build
  command, and doctests, from `AGENTS.md`, package scripts, or the `Makefile`.

## Workflow

1. **Pick one doc type** for the reader's need (the Diátaxis types, plus ADRs
   and READMEs). Do not mix types on one page; link between them instead.
   - **Tutorial:** a beginner learns by doing one guaranteed-to-work path, with
     no choices along the way.
   - **How-to guide:** a competent user reaches a specific goal; numbered steps,
     real-world variations, no teaching detours.
   - **Reference:** complete, accurate description of the machinery (API,
     flags, config keys, errors), structured like the code itself.
   - **Explanation:** background, design, trade-offs, and why.
   - **ADR:** one decision, recorded when it is made (template below).
   - **README:** what the project is and who it is for, a quickstart, where
     deeper docs live, how to get help and contribute, and the license.
2. **Extract facts from code.** Read the actual signatures, defaults,
   environment variables, flags, and error messages, and note the source file
   for each claim. If code and existing docs disagree, document what the code
   does and flag the mismatch to the user; it may be a bug.
3. **Draft in the project's voice.** Match heading case, person, tense,
   terminology, and formatting of nearby docs. State prerequisites and versions
   up front. Keep examples minimal and complete, and show expected output.
4. **Verify examples.** Run each documented command and snippet where it is safe
   (read-only, local, or in a scratch directory) and compare the output with the
   doc. Use the project's doc test support where it exists (Python doctest,
   `cargo test --doc`, Go `Example` functions). Do not run commands that deploy,
   spend money, need production credentials, or change shared state; mark them
   unverified in the report, and in the doc if the project has a convention for
   it. Label pseudo-code as illustrative.
5. **Check structure and links.** Relative links and anchors resolve, heading
   levels do not skip, images have alt text, and code fences name their
   language. Run the project's markdown lint and link checker if configured.
6. **Keep scope tight.** Change only the docs the task covers. List other stale
   or broken docs you noticed in the report instead of rewriting them.

## ADR template

Follow the project's existing ADR format if it has one. Otherwise:

```markdown
# ADR-NNNN: Short decision title

- Status: Proposed | Accepted | Deprecated | Superseded by ADR-NNNN
- Date: YYYY-MM-DD
- Deciders: names or roles

## Context

The problem, constraints, and forces that prompted the decision.

## Decision

What we will do, in full sentences ("We will ...").

## Consequences

What becomes easier or harder: costs, risks, and follow-up work.

## Alternatives considered

Each option, and why it was not chosen.
```

Once accepted, an ADR is not rewritten; a later ADR supersedes it, and only the
status line of the old one changes.

## Reference: relative link check

Illustrative. Prefer the project's link checker (for example `lychee --offline`
or markdown-link-check, if installed). This dependency-free script checks
inline links and images outside fenced code blocks; it does not handle
reference-style links or links inside inline code.

```python
"""Report relative Markdown links that point to missing files.

Usage: python check_links.py README.md docs/guide.md
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
FENCE = re.compile(r"^\s*(`{3}|~{3})")
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "#")


def relative_targets(text):
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK.finditer(line):
            target = match.group(1).strip("<>")
            if not target.startswith(EXTERNAL):
                yield target


def broken_links(doc):
    for target in relative_targets(doc.read_text(encoding="utf-8")):
        path = unquote(target.split("#", 1)[0])
        if path and not (doc.parent / path).exists():
            yield target


def main(paths):
    failures = 0
    for name in paths:
        doc = Path(name)
        for target in broken_links(doc):
            print(f"{doc}: broken link -> {target}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

If the project uses markdownlint-cli without a script, quote the glob so the
tool expands it: `markdownlint "**/*.md" --ignore node_modules`.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work: undo your own doc edits by
  editing them back, never with `git checkout` on doc paths.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including publishing a docs site.
- Never weaken a test, check, or lint rule to make work pass.
- Never document planned or unreleased behavior as current; label it as planned
  if the user wants it included.
- Do not change source code during a documentation task; report code issues
  instead.
- Never paste real secrets, tokens, or personal data into examples; use obvious
  placeholders.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Every documented command and snippet was run with matching output, or is
  listed as unverified with the reason.
- The doc build (if any), markdown lint, and link check pass for changed files.
- `git diff --stat` shows only the intended documentation files.

## Report

- **Files:** created or changed, with doc type and intended reader.
- **Sources:** the code, schemas, and commands each section is based on.
- **Verified:** commands and snippets run, with results.
- **Not verified:** commands not run and why.
- **Mismatches:** places where code and prior docs disagreed, and what you chose.
- **Follow-ups:** stale or broken docs noticed outside the scope.

## Optional delegation

The `doc-writer` subagent can draft or update assigned documentation paths in
parallel; review its sources and re-run its key commands before accepting the
draft. The `docs-researcher` subagent can fetch authoritative third-party docs
for the exact versions in the lockfile when a page depends on them.
