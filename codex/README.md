# Codex delegation adapter

The repository's `agents/*.md` files are portable role prompts. They are not a
native Codex agent registry. Codex's host application or API orchestrator must
create the delegated run, supply the role prompt, and enforce its permissions.

Use the dependency-free adapter to create a structured packet:

```bash
python scripts/codex_delegate.py \
  --agent reviewer \
  --task "Review commit range HEAD~1..HEAD for regressions and missing tests." \
  --files src tests \
  --format json
```

The packet contains the role metadata, bounded task, allowed paths, write mode
(`read-only`, or `scoped` when the role declares `Edit` or `Write`), required
evidence, and a ready-to-pass prompt. A native Codex
orchestrator can run independent packets in parallel, then have the main agent
validate and synthesize the reports.

The adapter never invokes a model, edits files, accesses credentials, or grants
permissions. The orchestrator remains responsible for approval, concurrency,
timeouts, retries, and final integration.
