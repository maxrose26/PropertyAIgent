# Publication dependency validation — INACTIVE B

Application remains frozen at db05f5d48ce0c70c048c99f538d8765dae669c17.
This owner-only change neither supplies a publication credential nor authorises B.

GitHub's 2026-10-02 stateless-installation-token rollout documents variable-length
opaque ghs_ tokens (approximately 520 characters); its 2026-04-24 notice says not
to decode or rely on JWT claims. A fixed 255-character ceiling is incompatible.
The shared owner predicate now accepts ghs_ graphic ASCII within local bounds
of 24–2048 bytes. These are local policy limits, not provider length guarantees.
The 4000-byte serialized credential pipe, 32768-byte encrypted vault, output
ceilings, independent one-mutation revocation and no-retry rules stay unchanged.
JSON expansion may still cause a safe refusal before the child starts.
Scope and actual expiry must come from a future trusted minting receipt.
Synthetic tests cover storage, handoff, parent/child intake and revocation only.

Official sources:
- https://github.blog/changelog/2026-10-02-stateless-github-app-installation-tokens-rolled-out/
- https://github.blog/changelog/2026-04-24-notice-about-upcoming-new-format-for-github-app-installation-tokens/
- https://docs.github.com/en/rest/apps/installations#revoke-an-installation-access-token

Exactly one credential-free hosted check is proposed on the fixed branch
validation/b-gh-official-2-103-3-20261101-01. It tests the unchanged pinned helper
against official gh 2.103.3 Linux amd64: checksum file plus archive under a shared
40-second/16000000-byte transfer ceiling, safe extraction/ELF/version/path checks
within 15 seconds, offline API help within 5 seconds, total 60 seconds.
No authentication is inherited by the test process. Only public release asset
GETs, gh --version and gh api --help are used; no authenticated API command.
Export is bounded to 64 KiB compressed nonsecret proof, no archive or binary.
Failure consumes this hosted check: preserve evidence, reconcile offline, do not
dispatch a replacement without separate approval. Hosted observations do not
prove the eventual Render build, allocation, connectivity or credential access.
