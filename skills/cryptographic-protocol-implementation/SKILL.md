---
name: cryptographic-protocol-implementation
description: "Implement or review application cryptography with vetted high-level libraries, covering authenticated encryption with key IDs for rotation, nonce strategy, signatures, key derivation, password hashing, TLS and mTLS configuration, and hybrid post-quantum key exchange. Use when code must encrypt, sign, derive keys, hash passwords, or configure TLS, or when existing crypto code needs checking for misuse. Not for a general security review (use the security-review skill) or a leaked key (use the secret-leak-response skill)."
---

# Cryptographic Protocol Implementation

Protect data with constructions that experts have already built and tested.
The stance is **library first**: choose the highest-level vetted API that
fits, design the ciphertext format for key rotation from day one, and prove
the result with published test vectors. Hand-assemble primitives only when no
vetted construction fits, and then follow a published specification exactly.

## When to use

- Encrypting fields, tokens, files, or backups in application code.
- Signing or verifying messages, webhooks, or tokens; deriving keys; storing
  passwords.
- Configuring TLS or mTLS for services and clients, or planning a
  post-quantum migration.
- Reviewing existing cryptographic code for misuse.

## When not to use

- A broad security review of a change: use the `security-review` skill.
- Deciding which threats need cryptographic controls: use the
  `threat-modeling` skill.
- A key or secret has leaked: use the `secret-leak-response` skill.
- Mapping encryption to compliance controls: use the `compliance-audit` skill.

## Inputs to gather

Discover from the repository first; ask only about what remains ambiguous.

- **Runtime and libraries:** language, framework, and the crypto libraries
  already in the manifests. Prefer a vetted library the project already uses.
- **What is protected:** the data, the attacker, and how long confidentiality
  must last (long-lived secrets raise the post-quantum priority).
- **Key management:** KMS, HSM, or secret manager; who can use keys; the
  rotation policy.
- **Interoperability:** existing ciphertext formats, other services or
  languages that must read the data, and protocol specifications to follow.
- **Constraints:** whether FIPS 140-3 validated modules are required (then use
  only the module's approved algorithms; XChaCha20-Poly1305 and Argon2id are
  not FIPS-approved), and expected message volume and size per key.

## Workflow

1. **Choose the construction.** Pick the highest-level option that fits:
   - Encrypting records or fields: libsodium
     `crypto_aead_xchacha20poly1305_ietf_encrypt` or `crypto_secretbox_easy`
     (PyNaCl `SecretBox`), a Google Tink AEAD keyset, or cloud KMS envelope
     encryption (a data key per object, wrapped by a KMS key).
   - Files, backups, and streams: age, libsodium `crypto_secretstream`, or
     Tink streaming AEAD.
   - Encrypting to a recipient's public key: libsodium sealed boxes, Tink
     hybrid encryption (HPKE), or age recipients.
   - Signatures: Ed25519, or ECDSA P-256 where interoperability or the
     validated module requires it.
   - Message authentication: HMAC-SHA-256.
   - Subkeys from a high-entropy secret: HKDF-SHA-256 (RFC 5869) with a
     distinct `info` label per purpose.
   - Passwords: Argon2id (step 5). Secure channels: TLS (step 6). Never design
     a handshake; if TLS does not fit, use a vetted Noise protocol library.
2. **Design the envelope for rotation.** Every ciphertext carries a format
   version, a key ID, the nonce, and the ciphertext with its tag. Authenticate
   the version, key ID, and context (table, column, record ID, tenant) as
   associated data so a ciphertext cannot be moved or relabeled. Decryption
   picks the key by ID and fails on unknown IDs. Rotation adds a new key, sends
   new writes to it, keeps old keys decrypt-only, re-encrypts in the background,
   and retires old keys only when no ciphertext or backup still needs them.
   Tink keysets and KMS envelope formats provide this for you.
3. **Get nonces right.** Never reuse a nonce under the same key: with AES-GCM
   or ChaCha20-Poly1305, reuse reveals the XOR of the plaintexts and enables
   forgeries.
   - With random 96-bit nonces (AES-GCM, ChaCha20-Poly1305), do not exceed
     roughly 2^32 messages per key (the NIST SP 800-38D bound for random IVs).
     Count usage or rotate well before that.
   - Prefer XChaCha20-Poly1305, whose 192-bit nonce makes random nonces safe
     at any realistic volume, or counter nonces whose state can never repeat
     across restarts, replicas, or restored snapshots. AES-GCM-SIV limits the
     damage of accidental reuse where it is available.
   - Generate nonces and keys from the OS CSPRNG (`crypto.randomBytes` or
     `crypto.getRandomValues`, Python `secrets`, Go `crypto/rand`, Rust
     `getrandom`). Never use `Math.random`, `random`, or timestamps.
4. **Authenticate before use.** No plaintext is used until tag verification
   succeeds. APIs that emit plaintext before the final check (for example Node
   `decipher.update`) must buffer until `final()` succeeds, or use a chunked
   construction such as secretstream or age. Return one generic error for
   every failure. Compare MACs and tokens in constant time
   (`crypto.timingSafeEqual` on equal-length buffers, Python
   `hmac.compare_digest`, Go `subtle.ConstantTimeCompare`).
5. **Hash passwords with Argon2id** through a maintained library that stores
   the salt and parameters in the encoded hash. Use at least the OWASP Password
   Storage Cheat Sheet minimum (for example m=19 MiB, t=2, p=1) or an RFC 9106
   recommendation (t=1, p=4, m=2 GiB, or t=3, p=4, m=64 MiB when memory is
   constrained), then tune upward within the login latency budget. Verify with
   the library's verify function and re-hash on login when parameters change.
   Where FIPS rules out Argon2id, use PBKDF2-HMAC-SHA-256 with the cheat
   sheet's current iteration guidance. bcrypt ignores input past 72 bytes.
6. **Configure TLS and mTLS.**
   - TLS 1.3 by default. Allow TLS 1.2 only for clients that need it, with
     ECDHE key exchange and AEAD suites. Disable SSL 3.0, TLS 1.0, and TLS 1.1.
   - Keep certificate and hostname verification on in every client. Flag
     `InsecureSkipVerify: true`, `verify=False`, `rejectUnauthorized: false`,
     and `NODE_TLS_REJECT_UNAUTHORIZED=0`.
   - For mTLS, require and verify client certificates against a dedicated CA,
     then authorize on the certificate identity (a SAN or SPIFFE ID), not on
     chain validity alone. Use short-lived certificates with automated renewal.
   - Certificate pinning is usually discouraged because rotations and CA
     changes cause outages. Consider it only for clients you control end to
     end (your own mobile app or agents): pin a CA or intermediate public key,
     ship backup pins, and keep a way to update pins remotely.

   ```go
   // Illustrative mTLS server configuration (Go crypto/tls).
   cfg := &tls.Config{
       MinVersion: tls.VersionTLS13,
       ClientAuth: tls.RequireAndVerifyClientCert,
       ClientCAs:  clientCAPool, // *x509.CertPool holding only the client-issuing CA
   }
   ```
7. **Plan for post-quantum.** For data that must stay confidential for many
   years ("harvest now, decrypt later"), enable hybrid key exchange such as
   X25519MLKEM768 through the TLS library. Recent Go releases, OpenSSL 3.5 and
   later, BoringSSL-based stacks, and major browsers support it, some by
   default; check the release notes for your version. Hybrid stays secure if
   either component holds. Never hand-roll ML-KEM (FIPS 203) or ML-DSA
   (FIPS 204); use your library's supported API when it exists.
8. **Handle keys carefully.** Load keys from the KMS or secret manager, never
   from source code, and never log them. Use separate keys per purpose. Zeroize
   key buffers where the language supports it (`sodium_memzero`, the Rust
   `zeroize` crate). In garbage-collected runtimes (JavaScript, Python, Go,
   Java), zeroization is best effort because the runtime may have copied the
   buffer and strings are immutable; keep keys in byte buffers, and prefer KMS
   or HSM operations so raw keys never enter the process.
9. **Retire weak algorithms.** No ECB, no unauthenticated CBC or CTR, no MD5 or
   SHA-1 where collision resistance matters (signatures, certificates,
   integrity of untrusted data), no RSA keys below 2048 bits, no fast hashes
   for passwords. SHA-1 can be justified for interoperability where collision
   resistance is not relied on, such as HMAC-SHA1 in HOTP and TOTP (RFC 4226,
   RFC 6238). Record each exception and its reason. When a weak algorithm is
   requested, explain the risk and propose a replacement; if interoperability
   truly requires it, isolate it behind a narrow function and plan the migration.

## Reference: ChaCha20-Poly1305 envelope with a key ID (TypeScript, Node)

Illustrative. Uses Node's built-in `crypto`; with random 96-bit nonces, rotate
each key well before 2^32 encryptions, or use libsodium XChaCha20-Poly1305
when one key encrypts unbounded volumes.

```typescript
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';

const FORMAT_VERSION = 1;
const NONCE_LEN = 12;
const TAG_LEN = 16;
const HEADER_LEN = 1 + 4 + NONCE_LEN; // version | key ID (uint32 BE) | nonce

export interface KeyRing {
  currentKeyId: number;      // used for new encryptions
  keys: Map<number, Buffer>; // 32-byte keys from a KMS or secret manager
}

// Authenticate the header plus caller context (for example "users.ssn:42"),
// so a ciphertext cannot be moved to another record or relabeled.
function aad(header: Buffer, context: string): Buffer {
  return Buffer.concat([header, Buffer.from(context, 'utf8')]);
}

export function seal(ring: KeyRing, plaintext: Buffer, context: string): Buffer {
  const key = ring.keys.get(ring.currentKeyId);
  if (!key) throw new Error('current key is not loaded');
  const header = Buffer.alloc(HEADER_LEN);
  header.writeUInt8(FORMAT_VERSION, 0);
  header.writeUInt32BE(ring.currentKeyId, 1);
  randomBytes(NONCE_LEN).copy(header, 5);
  const cipher = createCipheriv('chacha20-poly1305', key, header.subarray(5), {
    authTagLength: TAG_LEN,
  });
  cipher.setAAD(aad(header, context), { plaintextLength: plaintext.length });
  const body = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return Buffer.concat([header, body, cipher.getAuthTag()]);
}

export function open(ring: KeyRing, envelope: Buffer, context: string): Buffer {
  const fail = () => new Error('decryption failed'); // one error for every cause
  if (envelope.length < HEADER_LEN + TAG_LEN) throw fail();
  if (envelope.readUInt8(0) !== FORMAT_VERSION) throw fail();
  const key = ring.keys.get(envelope.readUInt32BE(1));
  if (!key) throw fail();
  const header = envelope.subarray(0, HEADER_LEN);
  const body = envelope.subarray(HEADER_LEN, envelope.length - TAG_LEN);
  const decipher = createDecipheriv('chacha20-poly1305', key, header.subarray(5), {
    authTagLength: TAG_LEN,
  });
  decipher.setAAD(aad(header, context), { plaintextLength: body.length });
  decipher.setAuthTag(envelope.subarray(envelope.length - TAG_LEN));
  try {
    // Release nothing until final() has verified the tag.
    return Buffer.concat([decipher.update(body), decipher.final()]);
  } catch {
    throw fail();
  }
}
```

## Guardrails

- Revert or delete only files you created in this session, and say so. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions:
  destroying or disabling a key (data encrypted under it becomes
  unrecoverable), re-encrypting production data, or changing TLS settings on
  production endpoints.
- Never weaken a test, check, or parameter to make work pass. Reduced
  password-hashing cost belongs only in clearly marked test configuration.
- Never invent a cipher, mode, padding scheme, or handshake, and never disable
  certificate verification, even temporarily.
- Never hard-code, log, or commit keys, passwords, or plaintext secrets; use
  placeholders in examples and reports.
- Do not run scans or handshake tests against systems the user has not approved.

## Verification

Use the project's own test runner from `AGENTS.md`, `CLAUDE.md`, package
scripts, or the `Makefile`. Run each check separately and report its real
result; never chain alternatives with `||`.

- **Known-answer tests** from the specifications, run as ordinary test cases:
  RFC 8439 (ChaCha20-Poly1305), RFC 5869 (HKDF), RFC 8032 (Ed25519), RFC 7748
  (X25519), and RFC 9106 (Argon2). Add Project Wycheproof vectors, which are
  JSON files, by loading them in the project's tests; there is no Wycheproof
  command to run.
- **Property tests:** round trip; flipping any byte of the version, key ID,
  nonce, ciphertext, tag, or context fails with the generic error; a wrong key
  fails; repeated encryptions produce distinct nonces; after rotation, old
  envelopes still decrypt and new ones carry the new key ID.
- **TLS tests:** handshakes fail for TLS 1.1, for a missing client certificate,
  and for a certificate from the wrong CA. Against an approved local or
  staging endpoint, `openssl s_client -connect host:port -tls1_3` should
  succeed and `-tls1_1` should fail. OpenSSL 3 clients refuse TLS 1.1 at the
  default security level, so add `-cipher 'DEFAULT@SECLEVEL=0'` to the TLS 1.1
  attempt, or its failure proves nothing about the server.
- **Misuse search:** look for `Math.random`, `createCipher(`, `ECB`, `md5`,
  `sha1`, `InsecureSkipVerify`, `verify=False`, and `rejectUnauthorized`, and
  triage every hit.

## Report

- **Constructions:** libraries and versions chosen, and why.
- **Envelope and rotation:** format, associated data, and the rotation procedure.
- **Nonces:** strategy and the per-key message limit.
- **Keys:** source, access, and handling, with zeroization marked best effort
  where the runtime cannot guarantee it.
- **Passwords:** algorithm, parameters, and measured hashing time.
- **Transport:** TLS versions, mTLS identity checks, and post-quantum status.
- **Tests:** vectors and property tests run, with results.
- **Exceptions:** any legacy algorithm kept, with its justification.
- **Not verified:** platforms, interop partners, or settings not tested.

## Optional delegation

The `security-reviewer` subagent can review the finished cryptographic code
independently, and the `test-writer` subagent can add known-answer and tamper
tests. Re-run their key checks before relying on them. One agent can complete
this workflow alone.
