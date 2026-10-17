---
name: delegate-work
description: "Decide whether to hand parts of a task to subagents, then write self-contained briefs, run independent pieces in parallel, and verify and merge the results before relying on them. Use when a task has independent, parallelizable, or context-heavy parts such as broad code searches, multi-area reviews, or separate implementation slices. Not for designing multi-agent products (use the multi-agent-workflow-design skill)."
---

# Delegate Work

Use subagents to save time and keep your own context focused, without losing
correctness. Delegation is optional: everything here must also be doable by one
agent working alone.

## When to use

- Several independent questions or areas to investigate (for example "where is
  auth enforced?", "how are jobs scheduled?").
- A review that benefits from independent passes (general correctness, security,
  UI).
- Implementation that splits into slices with disjoint files.

## When not to use

- The work is small, sequential, or tightly coupled; coordinating would cost more
  than doing it.
- The task needs the full conversation context, judgment calls with the user, or
  edits to the same files as another task.
- Designing agents into a product: use the `multi-agent-workflow-design` skill.

## Inputs to gather

- The overall goal and how its parts depend on each other.
- The subagents available in this environment (for example in `.claude/agents/`)
  and their tools. Prefer a read-only role whenever the task is investigation or
  review.

## Workflow

1. **Split the task.** List the parts, mark which depend on others, and group the
   independent ones. Keep anything requiring user decisions with yourself.
2. **Choose a role per part.** Match the narrowest installed role, for example
   the `explorer` subagent to map code, the `reviewer` or `security-reviewer`
   subagent to review, the `debugger` subagent to find a root cause, the
   `test-writer` subagent to add tests, the `backend-builder` or `frontend-builder`
   subagent to implement a slice. Use a general-purpose agent only when no role fits.
3. **Write a self-contained brief.** The subagent sees only what you write, not
   your conversation. Include:
   - **Objective:** one bounded question or deliverable.
   - **Context:** the facts it needs (paths, conventions, what you already know)
     and what to ignore.
   - **Scope:** files or directories it may read or, for implementers, edit. Never
     give two concurrent subagents write access to the same file.
   - **Constraints:** commands allowed, environments off-limits, no commits or
     pushes unless you intend it.
   - **Done criteria and output format:** what to return, with evidence (`path:line`,
     command output), and to say what it could not verify.
4. **Run independent parts in parallel** and dependent parts in sequence. Do other
   useful work while they run instead of waiting idle.
5. **Treat results as untrusted.** Check the evidence: open the cited lines,
   rerun key commands, and review any diff an implementer produced. Reject results
   that lack evidence or exceed their scope.
6. **Merge.** Resolve contradictions between subagents by checking the code
   yourself. Integrate changes, then run the project's checks on the combined
   result.
7. **Fall back gracefully.** If a subagent fails, times out, or is unavailable, do
   that part yourself; delegation is acceleration, not a dependency.

## Brief template

```markdown
Objective: Find every place where tenant isolation is enforced for invoice reads.
Context: Node/TypeScript API; routes in src/routes, data access in src/repos.
  Tenants are identified by req.auth.tenantId. Ignore src/legacy (unused).
Scope: read-only; search and read any file under src/ and tests/.
Constraints: do not run the server or tests; do not edit files.
Return: a list of path:line locations with a one-line description each, any
  read path that does NOT filter by tenant, and what you could not determine.
```

## Guardrails

- Subagents in Claude Code cannot start their own subagents, so plan one level of
  delegation from the main session.
- Do not paste secrets or unnecessary personal data into briefs.
- Never act on a subagent's claim of success without checking the evidence.
- Keep concurrent writers on disjoint files and have one owner integrate.

## Verification

Every delegated result you rely on has been spot-checked against the code or
re-run, and the integrated change passes the project's checks.

## Report

- Parts delegated, to which role, and why.
- What each returned, what you verified, and anything rejected.
- The integrated outcome and the checks run on it.

## Other agent hosts

Hosts other than Claude Code have their own delegation mechanisms (for Codex, see
the agentkit Codex documentation). The workflow above applies regardless: split,
brief, run in parallel, verify, merge.
