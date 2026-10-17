---
name: write-ops-script
description: "Write or harden an operational script in Bash, PowerShell, Python, or Node for data fixes, backfills, bulk API calls, cleanup, or environment setup: strict error handling, quoting, guarded paths, a dry run by default with an explicit apply flag, a required target with a confirmation that names it, idempotent and resumable batches, rate limits, logging, and exit codes. Use when writing or reviewing a one-off or repeated ops script. Not for the production data change itself (use the production-data-fix skill) or source rewrites (use the ast-manipulation-codemods skill)."
---

# Write Ops Script

Write a script that someone can run against a real system without fear: it
shows what it would do before doing it, refuses to guess its target, stops on
the first unexpected error, and can be re-run after a crash without doing
anything twice. The stance is **dry run by default, explicit target, safe to
re-run**.

## When to use

- A one-off or recurring operation: a data fix or backfill, bulk API calls,
  cleanup of files, records, or cloud resources, or environment setup.
- Reviewing or hardening an existing ops script before it runs against a shared
  or production system.

## When not to use

- Changing production data: use the `production-data-fix` skill for the
  approvals, backups, and verification around the change, and this skill for the
  script it runs.
- Rewriting source code across many files: use the `ast-manipulation-codemods` skill.
- Automation that belongs in CI or a scheduled pipeline: use the `ci-pipeline` skill.
- Schema or contract changes: use the `safe-migration` skill.
- Seed or fixture data: use the `synthetic-data-generation` skill.

## Inputs to gather

Discover these first; ask only about what remains ambiguous.

- The operation: exactly which records, files, or resources it touches, the
  expected count, what done looks like, and how to undo it.
- Target environments, how the script reaches each (credentials, endpoint,
  cloud profile, cluster context), and which one is production.
- Where it runs (laptop, bastion, CI job, container), its OS, shell, and
  runtime versions.
- Languages the team maintains and existing script conventions: location,
  helpers, argument style, logging, and lint configuration.
- Volume and limits: counts, API rate limits, maintenance windows, and load.
- A fixture, sandbox, or staging target to test against.

## Workflow

1. **Write the contract at the top of the script:** purpose, inputs, target,
   effects, idempotency, how to undo, and example dry-run and apply commands.
2. **Choose the language** the team maintains and the target host already has.
   Bash suits short glue around CLI tools on Linux or macOS; PowerShell suits
   Windows hosts; Python or Node (whichever the codebase uses) suits real logic,
   JSON, HTTP, retries, or anything longer than about a page of shell. Do not
   install a runtime on a host for one script.
3. **Design the interface.**
   - Dry run is the default. Changes happen only with an explicit `--apply` (or
     `--execute`), and the dry run prints exactly what apply would change.
   - The target is a required argument (`--env staging`) checked against a
     list, with no default, least of all production. Never take it silently
     from ambient state such as the current cluster context or default profile;
     print it.
   - Before applying, prompt with the target (and the planned count when it is
     cheap to compute), and require typing the target name. Non-interactive
     runs pass the same name (`--confirm staging`) rather than a bare `--yes`.
   - Offer `--limit` and `--batch-size` so the first apply can be small.
   - Read secrets from environment variables or the secret manager, never from
     arguments (visible in process lists and shell history), and never log them.
4. **Write it defensively** using the language notes below.
5. **Make it idempotent and resumable.**
   - Select only work still to be done (`WHERE region IS NULL`, a file not yet
     archived), and make each write a no-op when repeated: upserts, conditional
     updates, existence checks, idempotency keys on API calls.
   - Process in a stable order with keyset pagination (`id > last_id`), not
     offsets, which shift as rows change.
   - After each committed batch, checkpoint the last completed key per target,
     written atomically (temporary file, then rename), and resume from it.
   - Save before-values (export, backup table, or log) when the change cannot
     be recomputed backwards.
6. **Batch and throttle.** Size batches and pauses from the provider's rate
   limit or the project's policy; for example 100 to 1,000 rows per batch with
   a short pause. Keep one transaction per batch, not one for the whole run.
   Honor `429` and `Retry-After`, retry only transient errors with capped
   backoff, and stop after a set number of failures.
7. **Log and exit clearly.** Log the target, mode, arguments (never secrets),
   and start time; one line per planned or applied change with its key and old
   and new values (redact personal data); and a final count of changed,
   skipped, and failed items. Exit `0` only on full success; document other
   codes, for example `2` for usage errors and refused confirmation, which
   matches what `argparse` uses.
8. **Test before the real target.** Lint, run against a fixture, dry-run
   against staging and read the output, apply there with a small `--limit`,
   run it again to prove nothing changes, and interrupt and resume a run. Only
   then ask for approval to run against production, dry run first.
9. **Hand it over** with the exact commands, dry-run output, expected counts,
   and the undo path. Ask whether a one-off belongs in the repository.

### Bash

- Start with `set -euo pipefail`, and know where `set -e` does not stop the
  script: conditions of `if` and `while`, all but the last command of `&&` and
  `||` lists, after `!`, and functions called from those places. `local x="$(cmd)"`
  and `echo "$(cmd)"` hide the failure of `cmd` (declare, then assign).
  `((n++))` fails when `n` was 0 (use `n=$((n + 1))`). `grep` exits 1 on no
  match, so handle that case explicitly.
- Quote every expansion (`"$var"`, `"${files[@]}"`, `"$(cmd)"`), put `--`
  before path arguments, and use `[[ ]]` for tests.
- Guard every variable used in a path that will be deleted or overwritten.
  `${dir:?}` aborts when it is unset or empty, so `rm -rf -- "${build_dir:?}/cache"`
  can never become `rm -rf /cache`. Also check the path is under the expected
  root and refuse `/` and `$HOME`. Prefer deleting a reviewed list of files or
  moving them to a quarantine directory; recursive deletion is a destructive
  step that needs approval.
- Create temporary files with `mktemp` and remove them in a `trap ... EXIT`
  handler; never use fixed names in `/tmp`.
- Iterate with globs or `find ... -print0` and `while IFS= read -r -d '' f`;
  never parse `ls`.
- Run `shellcheck` if it is available, and fix findings rather than disabling them.

### PowerShell

- Start with `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`.
  Declare the target as
  `[Parameter(Mandatory)][ValidateSet('dev', 'staging', 'production')][string]$Environment`
  and the apply flag as `[switch]$Apply`.
- `'Stop'` makes cmdlet errors terminating, but a native program (`git`,
  `kubectl`, `az`) that exits non-zero does not throw in Windows PowerShell 5.1.
  Check after each one: `if ($LASTEXITCODE -ne 0) { throw "git failed: $LASTEXITCODE" }`.
  Newer PowerShell 7 releases add `$PSNativeCommandUseErrorActionPreference`;
  check `Get-Help about_Preference_Variables` for your version.
- `[CmdletBinding(SupportsShouldProcess)]` adds `-WhatIf` and `-Confirm`; wrap
  each change in `if ($PSCmdlet.ShouldProcess($target, 'Archive'))`. Keep the
  `-Apply` switch too, because `-WhatIf` is opt-in.
- Build paths with `Join-Path`, and use `-LiteralPath` for names that may
  contain `[` or `]`. Run `Invoke-ScriptAnalyzer` (PSScriptAnalyzer) if installed.

### Python and Node

- Python: `argparse` with explicit flags (`--env` with `choices` and
  `required=True`, `--apply` as `store_true`), `logging` for the record, and
  `sys.exit(main())`. Run commands with `subprocess.run([...], check=True)` and
  an argument list, never `shell=True` with interpolated input. Set a timeout on
  every network call.
- Node: `parseArgs` from `node:util` in recent Node.js versions (check yours)
  or the project's argument library. Await every promise, catch at the entry
  point, log, and set `process.exitCode = 1`. Use `execFile` or `spawn` with an
  argument array, not `exec` with a built string.

### Portability

- GNU and BSD (macOS) tools differ: `sed -i` (BSD needs `sed -i ''`), `date -d`
  versus `date -v`, `readlink -f`, `grep -P`, `xargs -r`, and `stat` formats.
  Use POSIX options, branch on `uname`, or move the logic to Python.
- macOS ships Bash 3.2: no `declare -A`, and before Bash 4.4 expanding an empty
  array under `set -u` is an error.
- Give `mktemp` an explicit template (`mktemp "${TMPDIR:-/tmp}/name.XXXXXX"`);
  that form works with both GNU and BSD.
- Windows: backslashes, spaces, and drive letters in paths, case-insensitive
  file systems, and differences between PowerShell 5.1 and 7 such as default
  file encodings.
- A Bash script saved with CRLF line endings fails with `$'\r': command not found`;
  set `*.sh text eol=lf` in `.gitattributes`.

## Worked example: Bash with dry run, guards, and trap

Illustrative: moves old log files into an archive directory and never
overwrites, so a re-run skips what is done. Checked with `bash -n`.

```bash
#!/usr/bin/env bash
# archive-logs.sh: move *.log files older than N days into an archive directory.
# Dry run by default; --apply moves files.
set -euo pipefail

usage() { echo "usage: $0 --dir DIR --archive DIR [--days N] [--apply]" >&2; exit 2; }

dir="" archive="" days=30 apply=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)     [[ $# -ge 2 ]] || usage; dir="$2"; shift 2 ;;
    --archive) [[ $# -ge 2 ]] || usage; archive="$2"; shift 2 ;;
    --days)    [[ $# -ge 2 ]] || usage; days="$2"; shift 2 ;;
    --apply)   apply=true; shift ;;
    *)         usage ;;
  esac
done

# Guards: stop on empty values before any path is built from them.
: "${dir:?--dir is required}" "${archive:?--archive is required}"
[[ "$days" =~ ^[0-9]+$ ]] || usage
[[ -d "$dir" && -d "$archive" ]] || { echo "error: both directories must exist" >&2; exit 2; }

list="$(mktemp "${TMPDIR:-/tmp}/archive-logs.XXXXXX")"
trap 'rm -f -- "$list"' EXIT   # runs on every exit, including errors

# NUL-separated names survive spaces and newlines; never parse ls.
find "$dir" -maxdepth 1 -type f -name '*.log' -mtime +"$days" -print0 > "$list"

count=0 skipped=0
while IFS= read -r -d '' file; do
  dest="$archive/${file##*/}"
  if [[ -e "$dest" ]]; then            # never overwrite; safe to re-run
    echo "skip, exists: $dest" >&2
    skipped=$((skipped + 1))
    continue
  fi
  if [[ "$apply" == true ]]; then
    mv -- "$file" "$dest"
    echo "moved: $file -> $dest"
  else
    echo "would move: $file -> $dest"
  fi
  count=$((count + 1))
done < "$list"

if [[ "$apply" == true ]]; then
  echo "moved $count, skipped $skipped" >&2
else
  echo "dry run: would move $count, skipped $skipped; pass --apply to move" >&2
fi
```

## Worked example: Python skeleton with --apply

Illustrative: fill in `fetch_batch` and `apply_fix` for the project. Checked
with `python -m py_compile`.

```python
#!/usr/bin/env python3
"""Backfill a missing field in batches. Dry run unless --apply."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("backfill")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True, choices=("dev", "staging", "production"))
    p.add_argument("--apply", action="store_true", help="write changes; default is a dry run")
    p.add_argument("--confirm", metavar="ENV", help="non-interactive confirmation; must equal --env")
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--limit", type=int, help="stop after this many rows")
    p.add_argument("--pause", type=float, default=0.5, help="seconds between batches")
    return p.parse_args(argv)


def confirmed(env: str, given: str | None) -> bool:
    if given is not None:
        return given == env
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"Write changes to {env}? Type its name to continue: ").strip() == env
    except EOFError:
        return False


def fetch_batch(env: str, after_id: int, size: int) -> list[dict]:
    """Rows still needing the fix with id > after_id, ordered by id: {id, old, new}."""
    raise NotImplementedError("project-specific query")


def apply_fix(env: str, row: dict) -> None:
    """Write one fix idempotently: a row that is already fixed stays unchanged."""
    raise NotImplementedError("project-specific write")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.apply and not confirmed(args.env, args.confirm):
        log.error("not confirmed for %s; nothing changed", args.env)
        return 2
    checkpoint = Path(f"backfill.{args.env}.checkpoint.json")  # run from outside the repository
    after_id = 0
    if args.apply and checkpoint.exists():
        after_id = json.loads(checkpoint.read_text())["last_id"]
    verb = "updated" if args.apply else "would update"
    done = 0
    while args.limit is None or done < args.limit:
        size = args.batch_size if args.limit is None else min(args.batch_size, args.limit - done)
        rows = fetch_batch(args.env, after_id, size)
        if not rows:
            break
        for row in rows:
            if args.apply:
                apply_fix(args.env, row)
            log.info("%s id=%s: %r -> %r", verb, row["id"], row["old"], row["new"])
        after_id, done = rows[-1]["id"], done + len(rows)
        if args.apply:  # temporary file, then rename: a crash never leaves half a checkpoint
            tmp = checkpoint.with_name(checkpoint.name + ".tmp")
            tmp.write_text(json.dumps({"last_id": after_id}))
            tmp.replace(checkpoint)
        time.sleep(args.pause)
    log.info("%s %d rows in %s%s", verb, done, args.env, "" if args.apply else " (dry run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

An unexpected exception exits non-zero with a traceback, and the checkpoint
still marks the last completed batch, so the re-run resumes there; `apply_fix`
being idempotent makes the partly done batch safe to repeat.

## Guardrails

- Ask before running against any shared or production target, and before any
  apply outside local fixtures. Show the dry-run output and count with the request.
- Never default the target to production or infer it silently, and never add a
  flag that skips both the dry run and the confirmation.
- Recursive deletion, dropping data, and bulk outward-facing calls (emails,
  payments, webhooks) need approval each time; mark such lines
  `# requires approval` in any documentation you write.
- Never print or log secrets or full personal data.
- Revert or delete only files you created in this session, and say so. Never
  discard someone else's work.
- Never weaken a check to get a clean run: no `set +e` around the whole script,
  no `|| true` on a step that matters, no disabled lint rule without a reason.
- Keep checkpoints, logs, and temporary files outside the repository unless the
  project says otherwise.

## Verification

Run each check separately and report its real result; never chain alternatives
with `||`. Say which tools were not available.

- Syntax and lint: `bash -n` and `shellcheck` for Bash, `Invoke-ScriptAnalyzer`
  for PowerShell, `python -m py_compile` plus the project's linter for Python,
  `node --check` plus the project's linter for Node.
- A dry run against the fixture or staging lists exactly the expected items and
  count, and a read-only query or listing shows nothing changed.
- A small `--limit` apply changes exactly what the dry run listed, and an
  immediate re-run changes nothing.
- An interrupted run resumes from the checkpoint without repeating or skipping work.
- A missing argument, an unknown target, a refused confirmation, and an
  unreachable target each exit non-zero with a clear message and no changes.

## Report

- **Script:** path, language, purpose, and the dry-run and apply commands.
- **Safety:** target handling, confirmation, idempotency, checkpointing, rate
  limits, and the undo path.
- **Evidence:** lint results, fixture and staging dry-run and apply summaries,
  and re-run and resume results.
- **Approvals:** which runs against which targets were approved, and the status
  of any production run.
- **Not verified:** checks that could not run and why.

## Optional delegation

One agent can complete this workflow alone. The `reviewer` subagent can review
the script before its first apply, the `test-writer` subagent can add tests for
its logic, and the `security-reviewer` subagent can check credential handling.
