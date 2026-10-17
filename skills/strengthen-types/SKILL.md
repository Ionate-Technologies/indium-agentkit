---
name: strengthen-types
description: "Adopt or tighten static typing incrementally (TypeScript strict options, mypy or pyright strictness per module, Kotlin nullability, PHPStan or Psalm levels): measure the baseline, enable one option or directory at a time behind a CI ratchet, fix root types at boundaries with runtime validation, and avoid any and ignore floods without changing runtime behavior. Use when enabling strict mode, adding a type checker to untyped code, or reducing type errors. Not for compiler or framework upgrades (use the upgrade-dependencies skill)."
---

# Strengthen Types

Raise type-checking strictness step by step while CI stays green and runtime
behavior stays the same. The stance is **ratchet, do not rewrite**: measure
first, tighten one option or one module at a time, never let the error count
rise, and validate untrusted data at runtime, because the type checker cannot.

## When to use

- Turning on TypeScript `strict`, or options such as `strictNullChecks`,
  `noUncheckedIndexedAccess`, or `exactOptionalPropertyTypes`.
- Adding mypy or pyright to untyped Python, or raising strictness for some
  modules.
- Raising PHPStan or Psalm levels, tightening Kotlin nullability around Java
  code, or adding `// @ts-check` to JavaScript.
- Code full of `any`, casts, and ignore comments keeps letting type bugs through.

## When not to use

- Upgrading TypeScript, mypy, or a framework itself: use the
  `upgrade-dependencies` skill. A new compiler version can add errors, so land
  that upgrade separately first.
- Restructuring code for clarity: use the `refactor-code` skill, and keep
  refactors and typing in separate changes.
- Designing CI jobs and required checks: use the `ci-pipeline` skill.
- A real bug found while typing: record it, then fix it in its own change with
  the `test-first-change` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- Checker, version, and config: `tsconfig*.json` or `jsconfig.json`;
  `mypy.ini`, `setup.cfg`, `pyrightconfig.json`, or `pyproject.toml`;
  `phpstan.neon` or `psalm.xml`; Kotlin compiler options and detekt config.
- The type-check command from `AGENTS.md`, package scripts, or the `Makefile`,
  how CI runs it, and how code is built: `tsc` emit, or a transpiler (esbuild,
  swc, Babel) that strips types unchecked but still reads some tsconfig options.
- Libraries that read types at runtime: decorator metadata (NestJS, TypeORM,
  Angular, InversifyJS) and Python annotations read by pydantic, FastAPI,
  SQLAlchemy `Mapped[...]`, dataclasses, or attrs.
- Where untrusted data enters (HTTP, database rows, environment and config,
  queue messages, `JSON.parse`, browser storage), and who owns which modules.

## Workflow

1. **Measure the baseline.** Count errors for the current config, then with
   each candidate option added, in total and per directory (snippet below), and
   subtract the current count. Also count existing escape hatches: `any`, `as`
   casts, non-null `!`, `@ts-ignore`, `# type: ignore`, and `cast(`. This table
   is both the plan and the progress measure.
2. **Pick the order and scope.** Enable an option project-wide when its errors
   fit in one reviewable change; otherwise scope it.
   - TypeScript: a common order is `noImplicitAny`, `strictNullChecks`, the
     rest of `strict`, then `noUncheckedIndexedAccess` and
     `exactOptionalPropertyTypes`. Neither of the last two is part of `strict`,
     and both need `strictNullChecks` (`tsc` rejects
     `exactOptionalPropertyTypes` without it). Setting `strict: true` with
     individual options set to `false` lets you switch them on one at a time;
     it also enables any strict option a future compiler adds, so plan
     upgrades around that. Which options `strict` covers depends on the
     version; check the tsconfig reference for yours.
   - Scope TypeScript by directory with a second config, for example
     `tsconfig.strict.json` that extends the base, sets the stricter options,
     and includes only migrated folders, checked in CI with
     `tsc -p tsconfig.strict.json --noEmit`. `tsc` also checks every file the
     included files import, so migrate leaf modules first. In monorepos, use
     project references per package. For JavaScript, add `// @ts-check` per
     file with JSDoc types before converting files.
   - Python: start with global settings that today's code passes, then tighten
     per module (snippet below). Older mypy versions accept `strict` only in
     the global section, so listing individual options per module works across
     versions. For pyright, start in `basic` or `standard` mode, then list
     migrated paths in the `strict` setting or add `# pyright: strict` at the
     top of a file. Start with leaf modules and boundary modules.
   - PHP: raise PHPStan's `level` one step at a time, or lower Psalm's
     `errorLevel` (1 is the strictest), each with a baseline file.
   - Kotlin: add nullability annotations on the Java side, and check the Kotlin
     docs for your version on how the compiler treats them (for example
     `-Xjsr305=strict` for JSR-305 annotations). Block new `!!` with a lint
     rule.
3. **Ratchet in CI.** The error count must never rise, and should only fall.
   - Prefer a scope that is fully clean (zero errors) and blocks merges.
   - Where it is not clean yet, check known errors in as a baseline: PHPStan
     `--generate-baseline`, Psalm `--set-baseline`, or a baseline tool for
     mypy or pyright if the project adopts one (vet it with the
     `evaluate-new-dependency` skill). Otherwise commit a list of error
     fingerprints (file, error code, message, no line numbers) and fail on any
     new one. A bare count lets new errors hide behind fixed ones.
   - Lower the baseline in the same change that fixes errors. Propose CI
     changes, and ask before making a check required.
4. **Fix the root types at boundaries first.** Most downstream errors trace to
   a few untyped sources: `JSON.parse`, `response.json()`, database rows,
   `process.env` or `os.environ`, queue payloads, and untyped libraries. Type
   each once at the boundary and the downstream errors collapse.
   - Data from outside the process is untrusted. Validate it at runtime and
     derive the type from the validator (zod or valibot in TypeScript; pydantic
     in Python), or write a type guard (example below). A cast only silences
     the checker.
   - Generate types from the source of truth where possible: OpenAPI or GraphQL
     codegen, ORM or query-builder types, and the config schema. Never
     hand-edit generated types; fix the generator's input.
5. **Fix errors without changing behavior.**
   - Prefer `unknown` plus narrowing (`typeof`, `in`, `instanceof`,
     discriminated unions, type guards) over `any`. Use `satisfies`
     (TypeScript 4.9 and later) to check object literals without widening them.
   - A null error is a question: can the value really be missing? If yes,
     handle that case on purpose. If no, add an explicit check that throws a
     clear error. Do not paper over it with `?.`, `?? ''`, or `!`: optional
     chaining or a default turns a loud crash into silent wrong data, which is a
     behavior change.
   - In Python, narrow with `isinstance`, `TypeGuard` (3.10 and later), or
     `TypeIs` (3.13 and later, or from `typing_extensions`). Never validate
     untrusted data with `assert`, which `python -O` removes, and remember that
     `typing.cast` does nothing at runtime.
6. **Suppress narrowly and visibly.** When an error cannot be fixed now:
   - TypeScript: `// @ts-expect-error -- reason, TICKET-123`, not
     `@ts-ignore`; it fails once the error is gone, so stale suppressions
     surface. typescript-eslint's `ban-ts-comment` can require a description,
     and `no-explicit-any` and the `no-unsafe-*` rules flag new `any` and its
     unsafe use.
   - mypy: `# type: ignore[arg-type]  # reason, TICKET-123`, with
     `warn_unused_ignores` and the `ignore-without-code` error code enabled.
     pyright: `# pyright: ignore[ruleName]` with
     `reportUnnecessaryTypeIgnoreComment` on.
   - Count suppressions in the ratchet. Never bulk-insert ignores or `any` to
     reach zero; that hides the debt. Excluding a legacy module
     (`ignore_errors`, `// @ts-nocheck`, `exclude`) is a tracked, temporary
     scope decision, not a fix.
7. **Keep typing changes free of runtime effects.**
   - Do not change emit-affecting compiler options (`target`, `module`,
     `useDefineForClassFields`, `experimentalDecorators`,
     `emitDecoratorMetadata`, `verbatimModuleSyntax`, `esModuleInterop`) in a
     strictness change. If one must change, ship it separately with its own
     tests. `alwaysStrict`, part of `strict`, emits `"use strict"`, which can
     change how non-module scripts behave.
   - With `emitDecoratorMetadata`, declared parameter types become runtime
     metadata: changing a class type to an interface emits `Object` and can
     break dependency injection.
   - Replacing an `enum` with a union type removes a runtime object that code
     may iterate. `import type` is erased entirely, so a module whose import
     was previously kept (for example under `verbatimModuleSyntax`) no longer
     runs its side effects.
   - In Python, annotations can be behavior. A pydantic or FastAPI field
     changed from `Optional[str]` to `str` becomes required, and SQLAlchemy 2.0
     derives column nullability from `Mapped[...]` when `nullable` is not set,
     so a schema migration may follow. Moving imports under `TYPE_CHECKING` or
     adding `from __future__ import annotations` can break libraries that
     evaluate annotations at runtime.
8. **Type third-party code minimally.** Prefer the package's bundled types,
   then official stubs or `@types/*` packages that match the library's major
   version (`types-*` stub packages from typeshed in Python). Otherwise write
   minimal local declarations for only what the code uses, in a `types/` or
   `typings/` folder: a `declare module 'legacy-lib' { ... }` block or `.pyi`
   stubs (mypy's `stubgen` can draft them). Avoid the shorthand
   `declare module 'legacy-lib';`, which makes everything `any`, and scope
   `ignore_missing_imports` to the one module instead of setting it globally.
9. **Measure progress.** Re-run the baseline: errors per option, files or
   modules in strict scope, suppressions, and `any` counts. Report the trend
   and the next scope to migrate.

## Worked example (illustrative)

Errors per option in TypeScript, then the files with the most errors. The `sed`
pattern strips the `(line,col)` suffix and keeps folder names with
parentheses, such as Next.js route groups, intact.

```bash
npx tsc -p tsconfig.json --noEmit --pretty false | grep -c 'error TS'
for flag in noImplicitAny strictNullChecks; do
  printf '%s ' "$flag"
  npx tsc -p tsconfig.json --noEmit --pretty false "--$flag" | grep -c 'error TS'
done
npx tsc -p tsconfig.json --noEmit --pretty false --strictNullChecks \
  | grep 'error TS' | sed -E 's/\([0-9]+,[0-9]+\): error.*//' \
  | sort | uniq -c | sort -rn | head -20
```

For mypy, run the checker with one option added (for example
`mypy src --disallow-untyped-defs`) and count lines containing `: error:`.

Narrowing parsed JSON with a type guard instead of a cast:

```ts
type Order = { id: string; totalCents: number; status: 'open' | 'paid' };

function isOrder(value: unknown): value is Order {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>; // safe widening after the object check
  return (
    typeof v['id'] === 'string' &&
    Number.isInteger(v['totalCents']) &&
    (v['status'] === 'open' || v['status'] === 'paid')
  );
}

export function parseOrder(raw: string): Order {
  const data: unknown = JSON.parse(raw);
  if (!isOrder(data)) throw new Error('Order payload has an unexpected shape');
  return data;
}
```

For larger shapes, a schema library defines the check and the type once (for
example `z.infer<typeof OrderSchema>` with zod).

Lenient globally, stricter where migrated (mypy in `pyproject.toml`):

```toml
[tool.mypy]
python_version = "3.12"
check_untyped_defs = true
warn_unused_ignores = true
warn_redundant_casts = true
enable_error_code = ["ignore-without-code"]

[[tool.mypy.overrides]]
module = ["app.billing.*", "app.api.schemas"]
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_any_generics = true
warn_return_any = true

[[tool.mypy.overrides]]
module = ["legacy_vendor_sdk.*"]
ignore_missing_imports = true
```

Each module that becomes clean joins the strict `module` list in the same
change that fixes it.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including making a check required, changing emit-affecting compiler
  options, or adding a validation library or stub package (use the
  `evaluate-new-dependency` skill).
- Never weaken a test, check, or threshold to make work pass: no lowered
  levels, new excludes, bulk ignores, or `any` added to get to green.
- Keep typing changes behavior-neutral. If a fix needs a behavior change, stop,
  report it, and ship it separately with a test.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The type check passes for the migrated scope, the ratchet passes, and the
  baseline went down, not up.
- The test suite passes.
- Where `tsc` emits the build, build the base commit (for example from a
  separate `git worktree`) and the change into two folders outside the
  repository and diff them: type-only changes produce identical JavaScript, and
  every difference is explained. With another bundler, compare its build
  output the same way.
- For runtime-annotation libraries, the generated API schema (for example
  FastAPI's OpenAPI document) is unchanged, and the migration tool's
  autogenerate finds no new migration.
- Suppression and `any` counts did not rise, and every new suppression has an
  error code, a reason, and a ticket.

## Report

- **Baseline and result:** errors per option and per scope, before and after.
- **Enabled:** options and the files or modules now in strict scope.
- **Ratchet:** mechanism, baseline location, and CI job.
- **Boundaries:** sources typed, and the validators or guards added.
- **Suppressions:** added and removed, each with its ticket.
- **Runtime check:** emit or build diff result, and schema or migration checks.
- **Bugs found:** reported separately with `path:line`, not fixed in this
  change.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `test-writer` subagent can add characterization tests around a boundary
before a cast is replaced with validation. The `docs-researcher` subagent can
confirm version-specific compiler and checker options. The `reviewer` subagent
can check the diff for hidden behavior changes. The workflow above stays
complete for a single agent.
