# Owner-local storage acceptance handoff — PREPARED / UNUSED / HELD

Stage4 remains OPEN. This package does not release a live query, provisioning or rerun. Do not run the execution block until the exact scoped successor is released. Do not reuse either consumed registration or delete/rename any audit directory.

## Exact scope and remaining prerequisites

Integrated revision: 7cf8d32547b63d485de872afc2f717c3dce55322
Reviewed tree: 68bf766cda023b1f15a19a63978903995391ec46
Registration: 3779 bytes, SHA256 43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3
Immutable registration Git blob: 1580775c5bcf1060df07dde8cb32104d108e5f3d
Original expiry: 2026-10-18T08:54:58.469465Z = 18October09:54:58.469465BST.
New fixed audit/latch: ~/.local/state/propertyaigent/storage-acceptance-identity-successor-20261017

The specific release decision is whether to permit this one successor while preserving both earlier UNCERTAIN cleanup classifications. Both earlier attempts stopped before installation, password generation, protected-secret mapping or seed writes. The second acknowledged DB closure and empty/removed owned memory group; these facts do not retrospectively establish CLOSED. There is no unknown provisioning/seed/secret commit to repair. No new live diagnostic query is requested by this preparation.

Current production grant options, fixed-role/object absence, exact identity flags, transactional ownership transfer and ambient permissions remain mandatory in-controller gates. Metadata access does not prove protected-secret write/delete permission. A failed gate stops without stronger access or blind replay.

Remaining cumulative allowance: 238.71668903499903 supervised seconds;12 DB connection attempts. Prior spend1.2833109650009647 seconds/1connection/4commands/.26088705100028164 DBactive seconds/39returned data-value bytes is carried forward. Keep256MiB kernel actual-memory limit, swap0, phase and closure reserves, and2MiBcombined exported evidence with16KiB prior reservation. Data-value bytes are not wire traffic.

## Reuse prepared owner environment

Use the existing Linux/WSL terminal, keyring-authenticated gh, repository and venv. No new token, authentication-file copy, endpoint or credential is needed. The existing migration credential is entered only at the controller's hidden prompt. Never paste it or passwords/verifiers into chat, commands or files.

Both earlier events.jsonl files must remain byte-for-byte intact:
- ~/.local/state/propertyaigent/storage-acceptance-once-20261016/events.jsonl
- ~/.local/state/propertyaigent/storage-acceptance-memory-successor-20261017/events.jsonl

If the original expiry passes, stop. This binding cannot be renewed or replaced silently.

## Single execution block — HELD pending the specific release above

Preparation ends before exec systemd-run. That exec begins the finite production controller. It must not be run under the offline correction instruction.

```bash
(
    set -euo pipefail

    cd "$HOME/stage4-owner/pr122-storage-acceptance"
    test -z "$(git status --porcelain)"
    git fetch origin master
    git switch --detach 7cf8d32547b63d485de872afc2f717c3dce55322

    test "$(git rev-parse HEAD)" = 7cf8d32547b63d485de872afc2f717c3dce55322
    test "$(git rev-parse 'HEAD^{tree}')" = 68bf766cda023b1f15a19a63978903995391ec46
    test -z "$(git status --porcelain)"
    test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
    test ! -e "$HOME/stage4-owner/storage-identity-registration.json"
    test ! -e "$HOME/.local/state/propertyaigent/storage-acceptance-identity-successor-20261017"

    gh api \
      'repos/maxrose26/PropertyAIgent/git/blobs/1580775c5bcf1060df07dde8cb32104d108e5f3d' \
      --jq .content |
      base64 --decode > "$HOME/stage4-owner/storage-identity-registration.json"

    printf '%s  %s\n' \
      '43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3' \
      "$HOME/stage4-owner/storage-identity-registration.json" |
      sha256sum --check

    exec systemd-run --user --scope \
      --unit=propertyaigent-storage-memory-20261017 \
      -p Delegate=memory \
      -p MemoryMax=268435456 \
      -p MemorySwapMax=0 \
      -p OOMPolicy=kill \
      env PYTHONDONTWRITEBYTECODE=1 \
      "$HOME/stage4-owner/storage-controller-venv/bin/python" \
      -m verification.ingestion_storage.storage_controller \
      --authority AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016 \
      --accept-verifier-retention \
      --revision 7cf8d32547b63d485de872afc2f717c3dce55322 \
      --binding "$HOME/stage4-owner/storage-identity-registration.json" \
      --binding-sha256 43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3
)
```

## Outcomes and stop control

The controller runs grouped prerequisites → committed installation/readback → in-memory mapping → restricted activation → fixed3blocked items plus control → duplicate seed no-op → reconnect/readbacks and8denials → reviewed SQL revocation → exact protected-secret removals/name absence → session/socket/process/cgroup reconciliation.

Success requires STORAGE_ACCEPTED_ACCESS_DISABLED and CLOSED with positive closure evidence, exact4retained rows/0attempts/0executablegrants and preserved Salford stop. Each phase's durable intent/ack remains authoritative. Missing output is uncertain, not success.

On STOP_RECONCILE_NO_RETRY or any ambiguous DB, secret-store or teardown result, do not run again, compensate or delete evidence. Leave the credential-free audit intact and return only the summary JSON and audit. A user interrupt can leave partial effects: it is a stop, not a rollback guarantee.

No council calls, Application/factual writes, consumers, scheduling, deployment or stage advancement. Storage acceptance is not operational pipeline acceptance.
