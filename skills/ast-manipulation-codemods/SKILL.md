---
name: ast-manipulation-codemods
description: "Write, test, and run syntax-aware codemods (ast-grep, comby, jscodeshift, ts-morph, libcst, rust-analyzer) for large mechanical migrations such as API renames, import moves, and call-signature changes, with fixture tests, idempotency, and git diff as the review. Use when the same structural edit must land across many files. Not for judgment-driven restructuring (use the refactor-code skill)."
---

# AST Manipulation Codemods

Apply one mechanical change across a codebase with a tool that understands the
syntax, prove it on fixtures first, and leave a diff a human can review. The
stance is **fixtures before the bulk run, clean tree before the bulk run**: the
transform is tested on representative inputs, and it only runs on a working
tree whose `git diff` will show nothing but the codemod's output.

## When to use

- A rename, signature change, import move, or API migration repeated across
  dozens or hundreds of call sites.
- A library upgrade that ships, or needs, a codemod.
- A structural search ("every call to X with a literal second argument") that
  plain text search cannot answer reliably.

## When not to use

- Restructuring that needs judgment per site: use the `refactor-code` skill.
- Choosing or sequencing dependency upgrades: use the `upgrade-dependencies`
  skill, then return here for the mechanical part.
- A handful of call sites: edit them directly.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The exact before and after forms, with real examples copied from the codebase.
- Languages and file kinds in scope (`.ts`, `.tsx`, `.js`, `.py`, `.rs`) and
  what to exclude (generated code, vendored code, fixtures, `.d.ts` files).
- The project's formatter, type check, lint, and test commands from
  `AGENTS.md`, package scripts, or the `Makefile`.
- Whether a codemod already exists for this migration (library release notes
  often ship one).

## Workflow

1. **Inventory.** Search for every variant before writing the transform:
   aliases (`const log = logger`), optional chaining (`logger?.warn`), computed
   access, spread arguments, re-exports, and dynamic uses no codemod can see.
   Record counts; they are the baseline for the run. A text search such as
   `rg -n 'logger\??\.warn\(' src/` gives a first count; an `ast-grep` pattern
   gives a structural one (check `ast-grep run --help` for how your version
   selects `.ts` versus `.tsx` files).
2. **Choose the tool by need.**
   - Unambiguous literal rename (a unique package name or config key): plain
     search and replace is acceptable once a search shows every hit is the target.
   - Quick structural search and replace across languages: `ast-grep` or
     `comby`. Patterns match syntax, not text, and both preview before writing.
   - TypeScript and JavaScript with conditional logic: `jscodeshift` (export
     `parser = 'tsx'` for TypeScript), or `ts-morph` when the rewrite needs type
     information, such as whether `logger` is the application logger.
   - Python: `libcst`, which preserves comments and formatting; its
     `libcst.codemod` package includes a test base class for before and after cases.
   - Rust: rust-analyzer's structural search and replace for call-site
     rewrites; `syn` for custom tools, noting that `syn` drops ordinary
     comments, so run `rustfmt` and review comment loss.
3. **Write fixtures first.** Input and expected output pairs covering the main
   form, each edge case from the inventory, and no-op cases: already migrated
   code, look-alikes on other objects, and shapes the transform must leave alone.
4. **Implement narrowly.** Match the exact callee and shape. Mutate the matched
   nodes in place so comments and untouched code keep their formatting. For any
   shape the transform cannot handle with confidence, leave it unchanged and
   report its `path:line` instead of guessing.
5. **Test.** Run the fixture tests, then confirm idempotency: running the
   transform on its own output changes nothing.
6. **Dry-run on a slice.** Run against a few real files with preview output
   (`npx --no-install jscodeshift --dry --print --extensions=ts,tsx -t codemods/logger-warning.js src/billing/`)
   and read the result. jscodeshift processes only `.js` files unless
   `--extensions` says otherwise.
7. **Require a clean tree.** `git status --porcelain` must print nothing for the
   target paths. If it does not, stop and ask the user to commit or stash their
   work themselves; do not stash, reset, or check out files for them.
8. **Run in bulk, then format.** Run the codemod on the full scope, check the
   summary's error count (files that failed to parse were not transformed), and
   run the project's formatter.
9. **Verify and review the diff** (see Verification). Spot-check files from each
   variant in the inventory, and list every reported site that needs a human.
10. **If the result is wrong, do not revert it yourself.** Fix the transform on
    fixtures, report what the run changed, and let the user decide how to
    discard it. Because the tree was clean, the bulk run's changes are exactly
    the diff.

## Reference: jscodeshift transform and fixture test (illustrative)

Migrates `logger.warn(msg)` to `logger.warning({ message: msg })`. Calls whose
first argument is already an object are renamed only. Calls with extra
arguments are left unchanged and reported, because where those arguments belong
is a human decision. Idempotency is natural here: migrated calls are named
`warning` and no longer match.

```javascript
// codemods/logger-warning.js
module.exports = function transformer(file, api) {
  const j = api.jscodeshift;
  const report = api.report || (() => {});
  const root = j(file.source);
  let changed = false;

  const isLoggerWarn = (callee) =>
    (callee.type === 'MemberExpression' || callee.type === 'OptionalMemberExpression') &&
    !callee.computed &&
    callee.object.type === 'Identifier' &&
    callee.object.name === 'logger' &&
    callee.property.type === 'Identifier' &&
    callee.property.name === 'warn';

  root
    .find(j.Node)
    .filter((path) => path.node.type === 'CallExpression' || path.node.type === 'OptionalCallExpression')
    .forEach((path) => {
      const call = path.node;
      if (!isLoggerWarn(call.callee)) return;
      const [first, ...extra] = call.arguments;
      if (extra.length > 0 || (first && first.type === 'SpreadElement')) {
        report(`${file.path}:${call.loc ? call.loc.start.line : '?'} needs manual migration`);
        return;
      }
      call.callee.property = j.identifier('warning');
      if (first && first.type !== 'ObjectExpression') {
        call.arguments[0] = j.objectExpression([j.objectProperty(j.identifier('message'), first)]);
      }
      changed = true;
    });

  return changed ? root.toSource() : file.source;
};

module.exports.parser = 'tsx';
```

The `tsx` parser cannot read angle-bracket type assertions (`<Foo>bar`) in
`.ts` files; jscodeshift reports those files as errors, so handle them
separately. A plain identifier argument that already holds an object
(`logger.warn(ctx)`) looks like a message without type information; the
inventory step must find such sites, or the transform must use `ts-morph`.

```javascript
// codemods/__tests__/logger-warning.test.js (Jest)
const { applyTransform } = require('jscodeshift/dist/testUtils');
const transform = require('../logger-warning');

// Recast may print new objects across several lines; compare ignoring whitespace
// and let the project's formatter settle layout after the bulk run.
const squash = (s) => s.replace(/\s+/g, ' ').trim();
const run = (source) => applyTransform(transform, {}, { source, path: 'fixture.tsx' });

test.each([
  ["logger.warn('disk low');", "logger.warning({ message: 'disk low' });"],
  ["logger.warn({ message: 'x', code: 7 });", "logger.warning({ message: 'x', code: 7 });"],
  ['logger?.warn(msg);', 'logger?.warning({ message: msg });'],
  ["console.warn('x');", "console.warn('x');"],
  ['logger.warn(msg, err);', 'logger.warn(msg, err);'],
])('%s', (input, expected) => {
  expect(squash(run(input))).toBe(squash(expected));
});

test('a second run changes nothing', () => {
  const once = run("logger.warn('a');\nlogger?.warn(b);");
  expect(run(once)).toBe(once);
});
```

`defineInlineTest` from the same module works too when exact output formatting
is part of the expectation.

## Guardrails

- Run a bulk codemod only on a clean working tree, so `git diff` is the review.
- Never revert with `git checkout`, `git restore`, `git reset`, or `git stash`.
  Report what changed and let the user decide how to discard it. Delete only
  files you created in this session, such as the transform and its fixtures.
- Ask before running a codemod across more than the agreed scope, or across
  generated or vendored code, and before adding a codemod tool as a dependency.
- Never weaken a test, check, or type to make transformed code pass; a failure
  after a codemod is a transform bug or a site that needs a human.
- Leave unhandled shapes unchanged and report them; never guess.

## Verification

Use the project's own commands. Run each check separately and report its real
result; never chain alternatives with `||`.

- The fixture tests and the idempotency test pass.
- The bulk run's summary shows zero parse errors, or each error is listed.
- Remaining matches for the old form equal the reported manual sites (rerun the
  inventory search).
- Formatter, type check, lint, and the test suite pass on the transformed tree.
- `git diff --stat` touches only files in scope, and spot-checked hunks are
  correct, with comments preserved.

## Report

- **Tool and transform:** tool, version, and transform path.
- **Counts:** sites in the inventory, files changed, sites reported for manual work.
- **Verification:** each command and its result.
- **Manual follow-up:** each reported `path:line` and why it was skipped.
- **Not verified:** checks that could not run and why.

## Optional delegation

- The `explorer` subagent can run the inventory search in parallel while you
  write fixtures.
- The `reviewer` subagent can review a sample of the bulk diff independently.
