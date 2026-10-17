---
name: handle-file-uploads
description: "Build file upload, storage, processing, and download: direct-to-storage uploads with short-lived presigned URLs or POST policies, server-chosen keys, enforced size and type limits, content sniffing, private buckets with per-download authorization, safe serving of SVG and HTML, background image processing, malware scanning, safe archive extraction, quotas, and cleanup. Use when adding or hardening avatars, attachments, imports, or document storage. Not for provisioning buckets (use the infrastructure-as-code skill)."
---

# Handle File Uploads

Accept, store, process, and serve user files without turning storage into an
attack surface. The stance is **hostile until checked, private until
authorized**: the server decides every storage key, checks every file before it
becomes usable, and authorizes every download.

## When to use

- Adding avatars, attachments, documents, media, CSV or archive imports, or an
  "import from URL" feature.
- Moving uploads off the app server to direct-to-storage, or adding resumable
  or multipart uploads for large files.
- A review found public buckets, trusted filenames, stored XSS through SVG or
  HTML, missing size limits, or unbounded image processing.

## When not to use

- Provisioning buckets, bucket policies, CORS rules, encryption, and lifecycle
  rules: use the `infrastructure-as-code` skill. This skill says what they must
  contain.
- Reviewing an existing upload path for exploitable flaws, including SSRF: use
  the `security-review` skill.
- Queue, retry, and dead-letter mechanics for processing jobs: use the
  `background-jobs-and-queues` skill.
- How long files are kept and how they are erased: use the
  `data-retention-and-erasure` skill.
- Site-wide CSP and security headers: use the `browser-security-config` skill.
- Designing who may access which file: use the `access-control-design` skill.

## Inputs to gather

Discover these from the repository before asking. Ask the user only about what
remains ambiguous and would change the result.

- Storage provider and SDK (S3 or an S3-compatible store, GCS, Azure Blob), the
  existing buckets or containers, and how they are provisioned.
- Per file kind: allowed types, maximum size, maximum image dimensions, and
  per-user or per-tenant quota. These are product decisions; ask if missing.
- Who may read each file (owner, tenant members, share links, public after
  moderation) and the tenancy model.
- Existing job queue, image library (Pillow, sharp, libvips, ImageMagick),
  malware scanner, CDN, and frontend upload component.
- The data classification and retention policy for uploaded content.

## Workflow

1. **Choose the flow.** Prefer direct-to-storage: the client asks the API for
   an upload ticket; the API authorizes the request, checks quota, creates a
   `pending` file record, and returns a presigned PUT URL or POST policy for a
   server-chosen key; the client uploads to storage; a completion call or a
   storage event tells the API, which verifies the object and queues
   processing. Proxying through the app server is acceptable for small files
   with the same checks plus body-size limits at the proxy and the framework.
2. **Generate keys on the server**, for example
   `uploads/{tenant_id}/{random_uuid}`. Never derive a key or filesystem path
   from the client's filename: that invites path traversal, overwrites, and
   enumeration. Keep the original name only as metadata, sanitized for display
   and sent in `Content-Disposition` with an RFC 6266 `filename*` parameter.
3. **Scope the upload credential narrowly.**
   - Short expiry from the project's policy; for example 5 to 15 minutes.
   - One exact key and one method; never a bucket-wide or long-lived grant.
   - Size: S3 and GCS POST policies support a `content-length-range`
     condition. A presigned PUT binds `Content-Length` or `Content-Type` only if
     the SDK signs those headers; check your SDK. Where the credential cannot
     cap size, enforce it at completion and let a lifecycle rule remove
     unconfirmed objects.
   - Pin the allowed `Content-Type` in the signature or policy. It is still
     the client's claim, so step 4 checks the bytes.
4. **Verify before the file is usable.** On completion, stat the object and
   check that it exists, matches the pending record and its owner, and is
   within the size limit. Detect the type from magic bytes wherever it matters
   (for example libmagic through python-magic, `file-type` in Node, or Go's
   `http.DetectContentType`) and reject anything outside the allowlist;
   extensions and client MIME types are hints only. Move the record through
   `pending`, `scanning`, then `available` or `rejected`, and make every read
   path serve only `available` files.
5. **Process in a background job with limits**, never on the request thread.
   - Reject huge dimensions from the header before a full decode. Pillow warns
     above `Image.MAX_IMAGE_PIXELS` and raises `DecompressionBombError` above
     twice that; sharp has `limitInputPixels`. Set limits from product needs.
   - Run with a timeout and memory and CPU limits. With ImageMagick, restrict
     coders and resources in its `policy.xml`.
   - Re-encode images to normalize them, and strip metadata such as EXIF GPS
     unless the product needs it. Apply the orientation first (Pillow
     `ImageOps.exif_transpose`) so stripped images are not rotated.
   - Write derivatives to their own keys and make the job idempotent. Use the
     `background-jobs-and-queues` skill for retries and dead letters.
6. **Scan for malware where the risk warrants it:** files shared with other
   users, opened by staff, or downloaded to desktops. Scan before `available`
   with ClamAV or a managed option such as GuardDuty Malware Protection for S3
   or Microsoft Defender for Storage. Fail closed: a scan error leaves the file
   unavailable. Scanning reduces risk; it does not remove it.
7. **Extract archives safely (zip slip).** Resolve every entry's final path and
   reject it unless it is inside the target directory; reject links; cap entry
   count, per-entry size, and total uncompressed size while streaming, because
   header sizes can lie; do not recurse into nested archives without limits.
   Extract into a new temporary directory and delete it if extraction fails.
   For tar, recent Python versions offer `tarfile` extraction filters such as
   `filter="data"`; check your version's documentation.
8. **Treat "import from URL" as an SSRF sink.** Allow only expected schemes,
   resolve the host and block loopback, private, link-local (including the
   cloud metadata address `169.254.169.254`), and IPv6 equivalents, then
   connect to the address you checked so DNS rebinding cannot swap it.
   Re-validate every redirect or disable redirects, cap size and time, and
   fetch from an isolated worker. Use the `security-review` skill to review it.
9. **Authorize every download.** Keep buckets private with public access
   blocked. The download endpoint checks the caller's access to the file record
   on every request, then returns a short-lived presigned GET or streams through
   a proxy. Random keys are not access control. Mark private responses
   `Cache-Control: private` or `no-store` so shared caches do not keep them,
   and use signed URLs or cookies for private CDN content.
   Public files, such as moderated avatars, go to a separate public bucket or
   prefix by explicit decision.
10. **Serve user content safely.** HTML, SVG, and XML can run script in your
    origin (stored XSS). Serve user content from a separate domain that never
    receives the app's cookies, ideally a different registrable domain, and set
    `Content-Disposition: attachment` for anything not meant to render inline,
    `X-Content-Type-Options: nosniff`, and a `Content-Type` from your allowlist,
    never the client's. Presigned GETs can set these through response overrides
    such as S3's `response-content-disposition`. Show SVG inline only after
    rasterizing it or sanitizing it (for example DOMPurify with its SVG
    profile).
11. **Enforce quotas and clean up.** Check per-user or per-tenant count and
    bytes, including pending uploads, when issuing a ticket, and rate-limit
    ticket requests. Lifecycle rules abort incomplete multipart uploads and
    expire unconfirmed and temporary objects. In versioned buckets a delete
    leaves noncurrent versions until a lifecycle rule expires them. A scheduled
    job finds objects with no record and records with no object; it reports
    first and deletes only with approval.
12. **Test the abuse cases** listed under Verification, using synthetic files
    only.

## Worked example: bounded ZIP extraction (illustrative Python 3.9+)

```python
from __future__ import annotations

import stat
import zipfile
from pathlib import Path

MAX_ENTRIES = 1_000  # use the product's limits; these are examples
MAX_ENTRY_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
CHUNK = 64 * 1024


class UnsafeArchive(Exception):
    pass


def safe_extract(archive: Path, target: Path) -> list[Path]:
    """Extract a ZIP into a new, empty directory, rejecting traversal and bombs."""
    root = target.resolve()
    written: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as zf:
        entries = zf.infolist()
        if len(entries) > MAX_ENTRIES:
            raise UnsafeArchive("too many entries")
        for info in entries:
            if stat.S_ISLNK(info.external_attr >> 16):
                raise UnsafeArchive(f"link entry: {info.filename!r}")
            dest = (root / info.filename).resolve()
            if not dest.is_relative_to(root):  # Python 3.9+
                raise UnsafeArchive(f"path escapes target: {info.filename!r}")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            # Count real bytes while streaming; header sizes can lie.
            with zf.open(info) as src, open(dest, "xb") as out:  # "x": no overwrite
                while chunk := src.read(CHUNK):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_ENTRY_BYTES or total > MAX_TOTAL_BYTES:
                        raise UnsafeArchive("uncompressed size limit exceeded")
                    out.write(chunk)
            written.append(dest)
    return written
```

Entries such as `../../etc/cron.d/x` or `/etc/passwd` resolve outside `root`
and are rejected. A duplicate entry name fails the exclusive open instead of
overwriting an earlier file. Run this inside the processing job, never on the
request thread.

## Guardrails

- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  making a bucket or object public, changing bucket policy, CORS, or lifecycle
  rules in a shared environment, or deleting stored objects. Show a dry-run
  listing first and mark such commands `# requires approval`.
- Never weaken a test, check, or threshold to make work pass.
- Never trust the client's filename, extension, or MIME type, and never build a
  storage key or filesystem path from them.
- Never serve user-uploaded HTML or SVG inline from the application's origin.
- Never log presigned URLs; they work as bearer credentials until they expire.
  Log file record IDs and keys instead.
- Never use real users' files as fixtures. Generate scanner test files at test
  time instead of committing them, since they trip repository scanners.

## Verification

Use the project's own commands from `AGENTS.md`, `CLAUDE.md`, package scripts,
or the `Makefile`. Run each check separately and report its real result; never
chain alternatives with `||`.

- Upload tests: an oversized file is rejected by the policy or the completion
  check; a file whose bytes do not match an allowed type is rejected; a
  filename containing `../` is stored under a server key and displayed safely;
  an expired upload URL fails, and a second completion call for the same
  record is rejected.
- Download tests: another user or tenant gets a denial, an `available` check
  hides pending and rejected files, and an expired presigned URL fails.
- Serving tests: an uploaded SVG with a script is served as an attachment with
  `nosniff` and the allowlisted type, from the user-content domain.
- Processing tests: a decompression bomb and an oversized-dimension image are
  rejected within limits; derivatives carry no GPS metadata.
- Archive tests: traversal, absolute-path, link, and size-bomb archives are
  rejected; scanner tests fail closed on a scan error.
- Bucket settings, read from the IaC or the provider with read-only access,
  show public access blocked and the expected lifecycle rules.
- Type check, lint, and the project's test suite pass.

## Report

- **Flow:** direct or proxied, ticket expiry, key scheme, and completion path.
- **Limits:** size, type allowlist and detection method, dimensions, quotas.
- **Processing:** job, resource limits, metadata stripping, and derivatives.
- **Scanning and archives:** scanner and fail-closed behavior, extraction
  limits.
- **Access and serving:** download authorization, URL expiry, serving domain,
  and headers.
- **Lifecycle:** rules and orphan cleanup, with approvals obtained.
- **Verification:** each command and its result.
- **Not verified:** provider behavior assumed from documentation, environments
  not checked, and why.

## Optional delegation

The `security-reviewer` subagent can review the upload, serving, and URL-import
paths. The `infrastructure-reviewer` subagent can check bucket policy, CORS,
and lifecycle configuration. The `backend-builder` subagent can implement the
ticket and completion endpoints against an agreed contract, and the
`test-writer` subagent can write the abuse-case tests. One agent can complete
this workflow alone.
