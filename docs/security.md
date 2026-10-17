# Security policy

Treat every third-party skill, helper script, and reference as untrusted until
reviewed. Confirm its license, source, pinned revision, dependencies, network
behavior, file-system scope, and secret-handling behavior before redistribution.

Never commit credentials, private keys, access tokens, production data, or
unredacted logs. `scripts/validate_content.py` detects common credential shapes,
but it is not a complete secret scanner.

Keep review and verification agents read-only by default. Write-scoped
subagents (`backend-builder`, `frontend-builder`, `mobile-builder`,
`infra-builder`, `test-writer`, `doc-writer`) declare `Edit` and `Write` and must
change only the paths the parent assigns. `infra-builder` never applies
infrastructure changes and `mobile-builder` never publishes builds.
Every subagent has `Bash`, which frontmatter cannot restrict, so read-only and
path limits depend on each subagent's instructions and on the host's permission
settings; review those settings before running subagents unattended.

Skills and subagents must require explicit user authorization before
destructive operations, production access, dependency changes, external
messages, or publishing outside this repository's stated policy.
`scripts/validate_content.py` rejects destructive commands in their code blocks
unless the step is marked as approval-gated.

To report a vulnerability, open a private GitHub security advisory for this
repository rather than filing a public issue.
