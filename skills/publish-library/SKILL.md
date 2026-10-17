---
name: publish-library
description: "Prepare and publish a library or SDK to npm, PyPI, crates.io, Maven Central, or Go modules: an explicit public API surface, a SemVer and deprecation policy, packaging checks on the built artifact, declared runtime support, licensing, provenance, and publishing from CI with trusted publishing or scoped tokens, then a clean-install check. Use when releasing a package version, setting up package publishing, or changing what a package exports. Every publish needs explicit approval. Not for application deploys (use the deployment-safety skill)."
---

# Publish Library

Ship a package version that contains exactly the intended public API, installs
cleanly on every supported runtime, and can be traced to the commit and CI run
that built it. The stance is **the published artifact is the contract, and a
version is forever**: inspect what consumers will download, not the repository,
and publish only with explicit approval because a version usually cannot be
replaced.

## When to use

- Cutting a release of a library, SDK, CLI package, or plugin.
- Setting up or moving package publishing to CI.
- Adding, removing, or renaming exports, entry points, or supported runtimes.
- A published version shipped wrong files, broken types, or a missing entry point.

## When not to use

- Writing the changelog or release notes: use the `release-notes` skill.
- An independent go or no-go on the release: delegate to the
  `release-engineer` subagent.
- Classifying API changes between versions: delegate to the
  `api-compatibility-checker` subagent.
- Signing, provenance, SBOMs, and registry account hardening in depth: use the
  `supply-chain-security` skill.
- Deploying a service or app: use the `deployment-safety` skill or, for app
  stores, the `mobile-release-safety` skill.
- Upgrading the package's own dependencies: use the `upgrade-dependencies` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- **Ecosystem:** `package.json` (npm, pnpm, Yarn), `pyproject.toml` or
  `setup.cfg` (PyPI, and the build backend), `Cargo.toml` (crates.io),
  `pom.xml` or `build.gradle(.kts)` (Maven Central), `go.mod` (Go modules).
  A monorepo may publish several packages.
- **Release tooling:** changesets, release-please, semantic-release, or a
  workflow in `.github/workflows/`; use it rather than a parallel process.
- **Published state:** current versions and dist-tags from the registry (for
  example `npm view <pkg> versions --json` and `npm view <pkg> dist-tags`).
- **Policy:** versioning rules (SemVer, pre-1.0 handling, whether type-only
  changes count as breaking), deprecation window, supported runtimes, license.
- **Who approves publishing** and who owns the registry package.

## Workflow

1. **Define the public API surface explicitly** and write it down, so a diff of
   the surface is reviewable:
   - npm: an `exports` map lists every importable subpath; anything unlisted
     cannot be imported. Adding `exports` to a package that had none is itself
     breaking for consumers who deep-import. Use `files` to allowlist published
     content.
   - Python: `__all__` in public modules, an underscore prefix for internals
     (`_internal/`), and a `py.typed` marker if the package ships types.
   - Rust: `pub` items reachable from the crate root; `pub(crate)` for
     internals. `#[doc(hidden)]` hides docs, not the item. Mark public enums and
     structs that may grow `#[non_exhaustive]`.
   - Go: exported identifiers outside `internal/` directories. A major version
     of 2 or more needs the `/vN` suffix in the module path.
   - Java: public types in exported packages (`module-info.java` `exports`);
     keep internals in packages named `internal`.
2. **Classify changes against the SemVer policy.** Delegate a full comparison
   to the `api-compatibility-checker` subagent when it is available. After 1.0,
   MAJOR includes more than removed exports:
   - renamed or removed exports, parameters, options, or fields;
   - signature changes: new required parameters, reordered positional
     parameters, a narrower accepted type, or a wider returned type;
   - new required members on an interface or trait that consumers implement;
     in Rust, new variants on an exhaustive enum or new fields on an exhaustive
     struct;
   - changed defaults, error types, error codes, or documented messages;
   - dropped runtime or platform versions, or a raised peer dependency major;
   - module format changes (for example CommonJS to ESM-only) and new or
     narrowed `exports` maps;
   - a dependency's major bump when its types appear in your public API.

   MINOR is new compatible functionality and new deprecations; PATCH is
   compatible fixes. Before 1.0, follow project policy; npm and Cargo caret
   ranges treat a `0.y` bump as breaking.
3. **Deprecate before removing.** Mark the old API in code (`@deprecated` in
   JSDoc, `warnings.warn(..., DeprecationWarning, stacklevel=2)` or
   `warnings.deprecated` on Python 3.13 and later,
   `#[deprecated(since = "...", note = "...")]` in Rust,
   `@Deprecated(since = "...", forRemoval = true)` in Java, a
   `// Deprecated:` paragraph in Go), keep it working for at least one minor
   release, document the migration, and remove it only in the next major.
   Python hides `DeprecationWarning` outside `__main__` and test runners, so
   also state it in the changelog.
4. **Write the changelog entry** with the `release-notes` skill, including a
   breaking-changes callout with migration steps. Bump the version in every
   manifest and version constant that carries it.
5. **Declare supported runtimes** and test the oldest and newest in CI:
   `engines` in `package.json` (npm only warns unless `engine-strict` is set),
   `requires-python` in `pyproject.toml` (`python_requires` in `setup.py` or
   `setup.cfg`), `rust-version` in `Cargo.toml`, the `go` directive in `go.mod`,
   and the Java release level the build targets.
6. **Build once and inspect the artifact** consumers will download (commands
   below). Check that it contains no tests, fixtures, large data, `.env` or key
   files, or source maps you did not intend to ship; that every entry point,
   `bin`, and types file referenced by the manifest exists inside it; and that
   ESM and CommonJS conditions resolve to files in the right format, with the
   `types` condition first in each `exports` entry. Scan the extracted artifact
   for secrets. For Python, check wheel tags: a pure package builds
   `py3-none-any`; compiled extensions need platform wheels (for example built
   with cibuildwheel) and a buildable sdist. If installed, `publint` and
   `attw --pack` catch npm export and type mistakes; check `--help` for your
   versions.
7. **Check licensing.** A `LICENSE` file is in the artifact, the manifest
   declares an SPDX license expression in the form the build tool supports,
   a `NOTICE` file ships when the project has one (Apache-2.0 requires it to be
   passed on), and vendored third-party code keeps its license. Use the
   `dependency-audit` skill for dependency license compatibility.
8. **Publish from CI, not a laptop.** A tag or release-tool workflow builds the
   artifact once from the tagged commit, tests it, and publishes that same
   artifact from a separate job in a protected environment with required
   reviewers. Prefer trusted publishing (OIDC from CI, no stored token) where
   the registry supports it: PyPI does, and npm and crates.io have added it;
   check each registry's current docs. Otherwise use a granular token scoped to
   the package with an expiry, stored as a CI secret. Add npm provenance
   (`--provenance` from a supported CI provider with `id-token: write`) and
   attestations where available; use the `supply-chain-security` skill for
   signing and verification details. Maven Central requires signed artifacts,
   sources and javadoc jars, and complete POM metadata; follow Sonatype's
   current Central Portal guide.
9. **Choose the channel.** Publish pre-releases with an explicit `--tag next`
   (or `beta`) on npm so `latest` never points at one. PyPI pre-releases use
   PEP 440 versions (`2.0.0rc1`) that pip skips unless asked; Cargo and Go skip
   pre-release versions unless requested.
10. **Get explicit approval, then publish.** Show the package name, version,
    dist-tag or channel, the artifact file list, and the exact command or
    workflow run. Publishing is outward-facing and effectively irreversible: npm
    never allows a name and version to be reused even after an unpublish, PyPI
    never allows a file name to be reused, crates.io and Maven Central versions
    cannot be replaced, and the Go module proxy keeps a version once fetched.
11. **Verify after publishing** in a clean project outside the repository
    (commands below): install the exact version from the registry, import each
    public entry point in each supported module format, run a smoke test,
    confirm types resolve, check provenance (for example `npm audit signatures`),
    and confirm dist-tags point where intended.
12. **If a bad version shipped,** do not try to overwrite it. Publish a fixed
    patch, then deprecate or yank the bad one with approval (`npm deprecate`,
    PyPI yank, `cargo yank`, a `retract` directive in a new Go version). If it
    contained a secret, use the `secret-leak-response` skill first.

## Worked example: npm exports map for a dual ESM and CommonJS package

Illustrative. Separate type files per format keep TypeScript from resolving
ESM types for a `require` call.

```json
{
  "name": "@acme/widgets",
  "version": "2.3.0",
  "type": "module",
  "exports": {
    ".": {
      "import": { "types": "./dist/index.d.ts", "default": "./dist/index.js" },
      "require": { "types": "./dist/index.d.cts", "default": "./dist/index.cjs" }
    },
    "./package.json": "./package.json"
  },
  "files": ["dist"],
  "engines": { "node": ">=20" },
  "license": "MIT"
}
```

npm always includes `package.json`, the README, and the license file. Shipping
both formats risks two copies of module state if a consumer loads both; keep
state out of module scope or ship one format.

A Python deprecation that points at the caller (illustrative):

```python
from __future__ import annotations

import warnings


def connect(host: str, *, timeout: float = 10.0, timeout_ms: int | None = None) -> None:
    if timeout_ms is not None:
        warnings.warn(
            "connect(timeout_ms=...) is deprecated and will be removed in 3.0; "
            "use timeout= in seconds",
            DeprecationWarning,
            stacklevel=2,  # attribute the warning to the caller's line
        )
        timeout = timeout_ms / 1000
    ...
```

## Reference commands

Illustrative; run each separately and adapt names. Publishing lines run from CI
after approval.

```bash
# npm
npm pack --dry-run                                   # lists files and size
npm publish --provenance --access public --tag next  # requires approval; --tag only for pre-releases

# Python (the build and twine tools must be available)
python -m build
twine check dist/*
python -m zipfile -l dist/acme_widgets-2.3.0-py3-none-any.whl
tar -tzf dist/acme_widgets-2.3.0.tar.gz
twine upload dist/*                                  # requires approval; prefer trusted publishing

# Rust
cargo package --list
cargo publish --dry-run
cargo publish                                        # requires approval

# Go: the tag is the release; go mod tidy -diff needs Go 1.23 or later
go mod tidy -diff
git tag v1.4.0
git push origin v1.4.0                               # requires approval
GOPROXY=proxy.golang.org go list -m example.com/widgets@v1.4.0
```

Clean-install check, in an empty directory outside the repository:

```bash
npm init -y
npm install @acme/widgets@2.3.0
node --input-type=module -e "import('@acme/widgets').then((m) => console.log(Object.keys(m)))"
node -e "console.log(Object.keys(require('@acme/widgets')))"
npm audit signatures

python -m venv venv                                  # on Windows, use venv\Scripts\python below
venv/bin/python -m pip install "acme-widgets==2.3.0"
venv/bin/python -c "import acme_widgets; from importlib.metadata import version; print(version('acme-widgets'))"
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never publish, unpublish, deprecate, yank, move a dist-tag, or push a release
  tag without explicit approval. Mark such commands `# requires approval`.
- Never publish from a laptop when CI publishing exists, and never put registry
  tokens in the repository, `.npmrc` files that get committed, or logs.
- Never ship a breaking change in a MINOR or PATCH release after 1.0, and never
  remove a deprecated API before the announced version.
- Never publish an artifact other than the one built and tested from the tagged
  commit.
- Never weaken a test, check, or threshold to make work pass.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- The test suite passes on the oldest and newest supported runtimes.
- The artifact file list contains only intended files, and every manifest entry
  point exists in it.
- Packaging checks pass (`npm pack --dry-run`, `twine check`,
  `cargo publish --dry-run`, or the ecosystem's equivalent).
- The version is greater than every published version and is not already taken.
- After publishing: a clean install imports every public entry point, types
  resolve, and provenance or signatures verify where enabled.

## Report

- **Package and version:** name, version, dist-tag or channel, registry.
- **Public surface:** exports added, removed, or deprecated, and the bump rationale.
- **Artifact:** file list summary, size, entry points, and wheel tags or formats.
- **Runtimes and license:** declared support and license files shipped.
- **Publishing:** CI run, authentication method (trusted publishing or token),
  provenance or signatures, and who approved.
- **Post-publish check:** clean-install commands and results.
- **Not verified:** runtimes, platforms, or registries not exercised.

## Optional delegation

The `api-compatibility-checker` subagent can classify API changes between the
previous release and the candidate. The `release-engineer` subagent can audit
readiness before tagging. The `dependency-auditor` subagent can check
dependency licenses and advisories. The workflow above stays complete for a
single agent.
