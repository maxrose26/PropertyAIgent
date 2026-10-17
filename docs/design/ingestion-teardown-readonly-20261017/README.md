# Exact read-only teardown reconciliation — owner-released, not executed here

Stage4OPEN. Owner approved one additional read-only observation after evidence1bb6734da94627db39a6a434a45e45ca5325b99d. No mutation or old-controller replay. No runtime integration/master movement.

Frozen helper SHA256cbe64e7394dda45f3940f5a66f68935687cc505069743ec1dc779523b8f1b3a2; Gitblob76420b396ccdd3af6478e0674c07c9e3104dbafc. Exact existing controller revision7cf8d32547b63d485de872afc2f717c3dce55322/tree68bf766cda023b1f15a19a63978903995391ec46. Original consumed registration43bb06... is inspected locally for its unchanged13bound hashes and expiry; it is not dispatched or reused. Separate durable once-latch storage-teardown-readonly-reconciliation-20261017, parent and child directories fsynced.

## Bound observation

- Max1DBconnection,6driver statements,10supervised seconds,256MiBfrom-exec kernel limit/swap0. Existing supervised8secondswork/2secondsclosure reserve. Carried prior cumulative6.463323766999565seconds/8connections/139commands; noreset of original10commandteardowncap.
- Existing approvedhost/port/database/CA/verify-full. Uses the exact selected IPv4 already recorded in the full prior hash-verified audit; no alternate route or DNS investigation. Existing migration credential through unchanged hiddeninput. No token/env/credential replacement.
- BEGIN READ ONLY; SET LOCAL statement_timeout2s; SET LOCAL idle_in_transaction_session_timeout3s; grouped safe identity/role/membership/session/permissionread; optional exact2role password-NULLboolean SELECT; ROLLBACK. At most6statements; no query text/password/verifier values selected. If password-column permission is unavailable, skip its SELECT and report UNKNOWN; no grant or stronger fallback.
- Raw safe observations are fsynced before migrationflag gate or disposition. Exactpostgres current/session and accepted4flags preserved. Only2runtime roles, memberships, session PID/backendstart/state/database/type and login/capability flags observed. Counts plus bounded17rows prevent silent truncation; larger counts remain visible, not accepted.
- One successful names-only GitHub environment-metadata GET, per_page100; jq exports only exact2temporarynames plus total_count. Failure,404 or cap remain UNKNOWN. No set/delete/other secret-value operation.
- Durable intermediate observation supervisor receipt explicitly separated from authoritative final-result.json, which is fsynced after localZIP archival and includes its SHA256 and total elapsed including bounded archival. A STOP exits nonzero; no automatic retry. Current observation closure never rewrites historical cleanup.
- Original expiry18October2026 09:54:58BST remains enforced before/after hiddeninput. Newbudget or expiry is notissued.

## Focused validation and independent review

12focused checks PASS (focused.xml): PostgreSQL parser verifies each data query is one SELECT, boolean-only password projection, truthful positive/negative/unknown dispositions, exclusive durable-latch/hashchain and actual officialgh2.45 names-metadata/API parsing with synthetic DBdriver for both6/5statement cases. PostgreSQL execution of these new queries is not claimed by these tests. Reuse existing acceptedkernel/CA/source bindings; no unrelatedsuite repeated.

Independent /root/migration_contract_review PASS for frozen SHAcbe64e7394dda45f3940f5a66f68935687cc505069743ec1dc779523b8f1b3a2. Parentdirfsync, finalresult-vs-intermediate evidence consistency, failed-connectUNCERTAIN and nonzeroSTOP findings resolved. No production operation performed by review.

## Exact owner command — one invocation authorised

Use existing WSLterminal/keyring/repo/venv; do not repeat authentication. No old audits/registrations are deleted or overwritten. This invokes only the read-only helper, not provisioning/storage_controller main.

```bash
(
    set -euo pipefail
    cd "$HOME/stage4-owner/pr122-storage-acceptance"
    test "$(git rev-parse HEAD)" = 7cf8d32547b63d485de872afc2f717c3dce55322
    test "$(git rev-parse 'HEAD^{tree}')" = 68bf766cda023b1f15a19a63978903995391ec46
    test -z "$(git status --porcelain)"
    test ! -e "$HOME/stage4-owner/storage-teardown-readonly.py"
    test ! -e "$HOME/.local/state/propertyaigent/storage-teardown-readonly-reconciliation-20261017"

    gh api \
      'repos/maxrose26/PropertyAIgent/git/blobs/76420b396ccdd3af6478e0674c07c9e3104dbafc' \
      --jq .content |
      base64 --decode > "$HOME/stage4-owner/storage-teardown-readonly.py"

    printf '%s  %s\n' \
      'cbe64e7394dda45f3940f5a66f68935687cc505069743ec1dc779523b8f1b3a2' \
      "$HOME/stage4-owner/storage-teardown-readonly.py" |
      sha256sum --check

    exec systemd-run --user --scope \
      --unit=propertyaigent-storage-memory-20261017 \
      -p Delegate=memory \
      -p MemoryMax=268435456 \
      -p MemorySwapMax=0 \
      -p OOMPolicy=kill \
      "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B \
      "$HOME/stage4-owner/storage-teardown-readonly.py"
)
```

At the hidden prompt enter the existing migration URL privately; never paste it in chat, commands, files or output. On anySTOP preserve allfiles; do not runagain.

## Full audit archival

Before credential input all3full original events.jsonl files are checked byte-for-byte and their complete hashchains verified:
-1573bytes/f509bd0d5a53282d099ca68b6d5ceb0e60047dd500991395779ba483621aafc0;
-7005bytes/5dda1e97c8dfc2a9a899c839e9c60d88f3c08bff05d5172579ad2efe1ade279e;
-104114bytes/788351d1bf68d282640a88f0c5627631a57b447bd4028db2ee781290ce73b560.

Finally the helper creates credential-free-audits.zip with their original bytes, the new read-only audit and HASHES.json, preserving sourcefiles untouched. Uncompressed originals/newaudit and ZIP are bounded300000bytes; no existing2MiBexportceiling increase. The authoritative final-result.json is a separate durable file binding that ZIPhash, avoiding circular hashes.

Return finalJSON and upload both credential-free-audits.zip and final-result.json from:
\\\\wsl.localhost\\Ubuntu-24.04\\home\\maxrose26\\.local\\state\\propertyaigent\\storage-teardown-readonly-reconciliation-20261017

The previous publication contains only an excerpt. Full archival in the repository is NOT complete until the owner transfers these files and their hashes are independently checked and the bytes published. No expiringCIartifact is used.

After readback return exactremaining cleanup and finite completionproposal. No login/permission/session/secret mutation is authorised by this read-onlyrelease. Originalstoragefunctionality verified; finalstorageacceptance conditional. IDs1504–1508/Salfordstop/historicaluncertainty unchanged; no consumers/source/scheduling/stageadvancement.
