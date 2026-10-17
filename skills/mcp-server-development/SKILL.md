---
name: mcp-server-development
description: "Build or review a Model Context Protocol (MCP) server that exposes tools, resources, or prompts to AI clients: SDK and transport choice, model-facing tool names, descriptions, and schemas, tool errors, authorization, least privilege, injection defenses, testing with the MCP Inspector, and backward-compatible versioning. Use when creating, extending, or auditing an MCP server. Not for application code that calls a model API directly (use the build-llm-feature skill)."
---

# MCP Server Development

Build an MCP server whose tools a model picks and calls correctly, and that stays
safe when the model, the client, or the data passing through it is hostile. The
stance is **design for the model, defend like a public API**: a few precise
tools, strict schemas, and server-side checks that never trust the caller.

## When to use

- Creating an MCP server that wraps an internal API, database, file store, or CLI.
- Adding or changing tools, resources, or prompts on an existing server.
- Reviewing an MCP server for tool design, security, or compatibility problems.

## When not to use

- Application code that calls a model API: use the `build-llm-feature` skill.
- A security audit of the wider service: use the `security-review` skill.
- Integrating an external REST API or webhook without MCP: use the
  `third-party-integration` skill.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the design.

- Who uses the server and how: local process launched by a desktop or IDE
  client, or a remote multi-user service.
- Language, SDK, and SDK version from the manifest and lockfile, and the protocol
  revisions that SDK version implements.
- The underlying system's API, authentication model, rate limits, and which
  operations read, write, or are destructive or outward-facing.
- For remote servers, the identity provider and how users map to permissions.
- Test, lint, and build commands from `AGENTS.md`, package scripts, or the `Makefile`.

## Workflow

1. **Scope the capabilities.** Map user tasks to MCP primitives: tools for
   model-invoked queries and actions, resources for read-only context identified
   by URI, prompts for user-invoked templates. Start with the smallest tool set
   that covers the tasks; do not mirror every endpoint of the underlying API.
2. **Choose the SDK and transport.** Use the official SDK for the language (the
   MCP project maintains TypeScript and Python SDKs among others). Package names,
   class names, and APIs change between major versions, so check the SDK docs
   for the installed version or delegate to the `docs-researcher` subagent.
   - **stdio** for local tools launched by the client: one user, credentials
     from the environment.
   - **Streamable HTTP** for remote or shared servers. The older HTTP+SSE
     transport is deprecated in recent spec revisions; keep it only for clients
     that still require it.
   - Recent revisions changed protocol fundamentals (for example, the 2026-07-28
     revision removed protocol-level sessions). Know which revisions your SDK
     and target clients speak before relying on a feature.
3. **Design each tool for a model reading it cold.**
   - **Name:** short and specific (`search_tickets`, not `query`). The spec
     recommends 1 to 128 characters from letters, digits, `_`, `-`, and `.`.
   - **Description:** what it does, when to use it instead of its siblings,
     argument formats with an example, limits, and what it returns. Nothing
     unrelated to the tool.
   - **Input schema:** required fields, enums for closed sets, numeric and
     length bounds, and patterns; reject unknown properties where the SDK
     allows. Prefer identifiers returned by another tool over free text.
   - **Output:** concise and structured, with the IDs needed for follow-up
     calls. Paginate or cap results, truncate long text with an explicit marker,
     and drop internal fields. If you declare an output schema and return
     structured content, also return the serialized JSON as text for older clients.
   - **Errors:** report input, business, and upstream failures as tool errors
     (results with `isError` set) whose message says what was wrong and what to
     do next, so the model can recover. Protocol errors are for unknown tools and
     malformed requests. A handler exception must never crash the server or
     return a stack trace.
4. **Make side effects safe.** Keep read and write tools separate. Make writes
   idempotent (natural keys or an idempotency key), offer a preview or dry run,
   and require confirmation for destructive or outward-facing actions, for
   example a preview call that returns a short-lived token the commit call must
   present, or elicitation where the client supports it. Annotations such as
   `readOnlyHint` and `destructiveHint` help clients, but clients must treat
   them as untrusted, so enforce the behavior on the server.
5. **Authenticate and authorize.**
   - **Remote servers:** follow the spec's authorization section. The server is
     an OAuth resource server: publish protected resource metadata, validate
     each token's signature, expiry, and audience, and reject tokens not issued
     for this server. Never pass a client's token through to upstream APIs; use
     the server's own credentials, scoped to the calling user.
   - **Any HTTP server:** validate the `Origin` header to block DNS rebinding;
     when running locally, bind to `127.0.0.1`, not all interfaces.
   - **stdio servers:** read credentials from the environment; the OAuth flow
     does not apply.
   - Authorize every call, including access to any state handle a previous call
     returned. Use least-privilege credentials (a read-only database role, a
     narrowly scoped API token).
6. **Validate and contain input.** Enforce the schema on the server, because
   not every client validates: confirm the SDK does it, or check in the handler.
   - **Paths:** resolve the path (following `..` and symlinks) and confirm it
     stays inside an allowed root.
   - **Commands:** no shell; pass an argument list to allowlisted executables,
     and reject values that start with `-` where they could become options.
   - **SQL:** parameterized queries, a read-only role where possible, row limits,
     and statement timeouts.
   - **URLs:** allowlist hosts; block private, loopback, link-local, and cloud
     metadata addresses to prevent server-side request forgery.
   - Rate limit per user and per tool, and cap output size.
7. **Protect secrets and the model's context.** Never return secrets, tokens,
   environment variables, or connection strings, including inside error
   messages. Content fetched from outside (web pages, tickets, email) can carry
   prompt injection into the client's model: return it as clearly labeled data
   and never add instructions to tool output. Tool descriptions are model
   context too, so review description changes like code.
8. **Log safely.** On stdio, stdout carries protocol messages only; write logs to
   stderr or a file. Log tool name, caller, duration, and outcome, not argument
   values that may hold secrets or personal data. The 2026-07-28 revision
   deprecates the protocol's logging feature in favor of stderr or OpenTelemetry.
9. **Test at three levels.** Unit test handlers as plain functions: valid input,
   each validation failure, permission denied, upstream failure, pagination,
   truncation, and injection-shaped input (`../`, absolute paths, shell
   metacharacters). Then exercise the server over its real transport with the
   SDK's client or the MCP Inspector (`npx @modelcontextprotocol/inspector`
   opens a local web UI; `--cli` suits scripts; check its README for current
   usage, and ask before downloading it). Finally run realistic tasks in a real
   client and check that the model picks the right tool with valid arguments.
10. **Version compatibly.** New tools, new optional arguments with defaults, and
    new output fields are additive. Renaming or removing tools or arguments,
    making an argument required, or changing output shape or meaning breaks
    clients and saved prompts: add a new tool, mark the old one deprecated in its
    description, and remove it in a major release. Return tools in a
    deterministic order, report the server version, and keep a changelog.

## Example: contained, model-friendly tools

Illustrative, written against the 1.x Python SDK's `FastMCP` API. Check your SDK
version: newer major versions rename the server class. In 1.x, `FastMCP` builds
the input schema from the annotated signature and validates arguments against it
on the server, and an exception raised in a tool reaches the model as a tool
error carrying its message.

```python
import os
import sys
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

NOTES_ROOT = Path(os.environ.get("NOTES_ROOT", "notes")).resolve()
MAX_CHARS = 20_000
mcp = FastMCP("notes")


def resolve_note(name: str) -> Path:
    """Map a note name to a file under NOTES_ROOT or raise an actionable error."""
    path = (NOTES_ROOT / name).resolve()  # follows ".." and symlinks
    if not path.is_relative_to(NOTES_ROOT) or path.suffix != ".md":
        raise ValueError(f"{name!r} is not a note name. Call list_notes for valid names.")
    if not path.is_file():
        raise ValueError(f"No note named {name!r}. Call list_notes for valid names.")
    return path


@mcp.tool()
def list_notes(limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[str]:
    """List note names, such as 'projects/plan.md', sorted alphabetically.
    Pass a returned name to read_note."""
    names = sorted(p.relative_to(NOTES_ROOT).as_posix() for p in NOTES_ROOT.rglob("*.md"))
    return names[:limit]


@mcp.tool()
def read_note(name: Annotated[str, Field(max_length=300)]) -> str:
    """Return the text of one note, by a name from list_notes.
    Notes longer than 20,000 characters are truncated with a marker."""
    text = resolve_note(name).read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_CHARS:
        return text[:MAX_CHARS] + f"\n[truncated {len(text) - MAX_CHARS} characters]"
    return text


if __name__ == "__main__":
    print(f"notes server reading {NOTES_ROOT}", file=sys.stderr)  # never stdout
    mcp.run()  # stdio transport by default
```

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including registering the server with shared clients or deploying it.
- Never weaken a test, check, or validation rule to make work pass.
- Never return secrets, accept tokens issued for another audience, or pass a
  client's token through to upstream services.
- Test destructive tools only against fixtures or a disposable environment.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Handler unit tests pass, including validation, permission, and injection cases.
- Listing tools over the real transport shows the expected names, descriptions,
  and schemas; a sample call to each tool succeeds, and a bad call returns an
  actionable tool error rather than a crash.
- On stdio, nothing but protocol messages reaches stdout.
- For remote servers: requests without a token, with an expired token, and with
  a token for another audience are rejected with 401.
- Lint, type-check, and build pass.

## Report

- **Capabilities:** each tool, resource, and prompt, with its purpose.
- **SDK and transport:** SDK version, protocol revisions supported, transport.
- **Security:** authentication, authorization, input containment, rate limits,
  and confirmation for destructive tools.
- **Compatibility:** changes to existing tools and whether any are breaking.
- **Verification:** each command and its result, and clients tested.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `docs-researcher` subagent can confirm SDK and spec details for the exact
versions in use. The `security-reviewer` subagent, or the `security-review`
skill, can review authorization and injection defenses; the `threat-modeling`
skill helps when tools act on production systems. The `test-writer` subagent
can add handler tests. One agent can finish this workflow alone.
