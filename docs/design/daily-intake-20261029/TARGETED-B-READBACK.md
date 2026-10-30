# PropertyAIgent — targeted B readback (INACTIVE)

Stage 4 OPEN. A acceptance and both inspection attempts are preserved. This package does not authorise a connection or any mutation. No production access occurred in its preparation.

## Exact files and provenance

Base candidate: 405f77f078a64175e037bd2e735de30658c1437f; tree 7a315b6a3388737d88498e69dc43d7282f74a95f.

Supplement SQL SHA-256: `d1b27618257b6d9f00cd72ce170e02f7aaae6e6dadae326cccbd099577989346`.
Supplement client SHA-256: `a8bda527d52ec2055935e4eacd6d6b6ff8722f35989c80032db42d0857a896a0`.

The original b-readonly.sql (131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997) and repository client are untouched. The separate fixed client has exactly three string substitutions: SQL filename (including its docstring), SQL hash, and PGAPPNAME. No argument accepting arbitrary SQL, bypass, controller, lifecycle action or retry is introduced. Its capture function and all connection/password/timeout/output handling are identical to the tested original. Python syntax and exact reverse-substitution equivalence checked offline. The supplement is covered by focused disposable PostgreSQL tests in the existing daily-intake-pg job. Validation results must identify the exact published head; no production observation is inferred from fixture results.

## Preparation and inactive invocation

Extract the ZIP into a NEW directory outside the checkout. Keep the SQL and client together. The following block is for a separately approved execution, not for current preparation. The package path is prompted locally; enter the absolute path of the extracted directory containing the two files.

```bash
(
set +x
set -eu
umask 077
repo="$HOME/stage4-owner/b-inspection-405f77f"
read -r -p 'Absolute extracted targeted package directory: ' package
case "$package" in /*) ;; *) printf 'STOP: absolute path required\n'; exit 1;; esac
cd "$repo"
test "$(git rev-parse HEAD)" = 405f77f078a64175e037bd2e735de30658c1437f
test "$(git rev-parse 'HEAD^{tree}')" = 7a315b6a3388737d88498e69dc43d7282f74a95f
test -z "$(git status --porcelain)"
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -S - "$repo" "$package" <<'PY'
from pathlib import Path
import hashlib,sys
r,p=map(Path,sys.argv[1:])
check=lambda path,h: hashlib.sha256(path.read_bytes()).hexdigest()==h
base=r/'docs/design/daily-intake-20261029'
assert check(base/'b-readonly.sql','131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997')
assert check(p/'b-targeted-readonly.sql','d1b27618257b6d9f00cd72ce170e02f7aaae6e6dadae326cccbd099577989346')
assert check(p/'b-targeted-readonly-client.py','a8bda527d52ec2055935e4eacd6d6b6ff8722f35989c80032db42d0857a896a0')
ca=r/'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt'
assert check(ca,'700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7')
s=(base/'b-readonly-client.py').read_text()
s=s.replace('b-readonly.sql','b-targeted-readonly.sql').replace('131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997','d1b27618257b6d9f00cd72ce170e02f7aaae6e6dadae326cccbd099577989346').replace("'propertyaigent-b-readonly'","'propertyaigent-b-targeted-readonly'")
assert s==(p/'b-targeted-readonly-client.py').read_text()
print('LOCAL_BINDINGS_VERIFIED; NO_DATABASE_CONNECTION_YET')
PY
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -S "$package/b-targeted-readonly-client.py"
)
```

When separately approved, answer the fixed client's prompts:

- Reviewed IPv4: `18.135.253.94` (the previously reviewed address, not a fresh DNS claim).
- CA: `/home/maxrose26/stage4-owner/b-inspection-405f77f/verification/ingestion_storage/trust/supabase-prod-ca-2021.crt`.
- Database identity: `postgres`.
- NEW private evidence directory: `/home/maxrose26/stage4-owner/b-targeted-evidence-405f77f-01` (must not already exist; do not delete previous evidence).
- Password: enter the existing password only at the hidden prompt; never the full URL or a chat message.

Fixed endpoint: aws-0-eu-west-2.pooler.supabase.com:5432; database postgres; routing user postgres.zcikcfgpblzuzpanpdqd. One psql connection, no retry, verify-full TLS, GSS disabled, 5-second connect timeout, psql -X -w and ON_ERROR_STOP. Fresh restricted client environment. SQL transaction is repeatable-read/read-only, statement timeout 3s, lock timeout 1s, idle transaction timeout 10s. Existing 60-second capture envelope reserves TERM at 58s/KILL one second later; combined output/status ceiling 65,536 bytes (psql allowance 64,512). Hidden password uses private 0600 temporary pgpass and is removed on normal context exit. Evidence stays in the owner-selected directory, not /tmp. Forced exits do not prove remote closure. Do not automatically rerun an incomplete inspection.

After execution, inspect locally:

```bash
python3 -m json.tool "$HOME/stage4-owner/b-targeted-evidence-405f77f-01/status.json"
cat -- "$HOME/stage4-owner/b-targeted-evidence-405f77f-01/psql-output.txt"
```

## Expected results and interpretation

Eight labelled result sets, in order, followed by ROLLBACK:

| Section | Required rows | Interpretation |
|---|---:|---|
| context | 1 | postgres session/database, read-only/repeatable-read. Full stats visibility required. Active observer RLS means coverage is not established by this package. |
| items | 2 | Both fixed keys found, exact fence/owner/authority/lease epoch, matching-fence attempt found and identities match. One matching attempt per key follows the retained composite primary key. NULL lease/fence or missing attempt is incomplete, not abandonment proof. Expiry compares to transaction timestamp. |
| sessions | 1 summary | Up to 32 records for worker/effect/application/recovery logins; total/reported match and complete=true. No query text, parameters, client address or password fields. Zero visible sessions only means none observed at that instant, not historical process closure. Missing visibility/state means incomplete. |
| recovery_access | 3 | Recovery login, recovery operator, and postgres. Role presence, login state, membership, inherited/set capability and EXECUTE are separate facts. No privilege is exercised or granted. NOLOGIN can be an expected closed state; false capability is a finding, not permission to activate. |
| functions | 2 summaries | Exactly one overload each. Oldham body expected 091ec5ee578083b0b64431542ec02ff8a39263d345dee6a360dde68d3622900a; recovery body expected 9e7f98210c737d6f8f7fae2d98e328261ab9faf31481f041b6f63befa6686f58. Both owner ingestion_storage_owner, SECURITY DEFINER, search_path=pg_catalog. Oldham: jsonb,text,text,jsonb / SQL stable; recovery: text,integer,boolean / plpgsql volatile. PUBLIC/worker/effect EXECUTE must not unexpectedly exist. Extra/missing overload or hash mismatch requires review. |
| stops | 1 | Exact candidate stop projection, missing-field flags, JSON types, effective intake global/manual predicates. Missing global_stop is blocking; JSON null is not. Any non-NULL manual_stop text, including an empty string, blocks intake under the candidate predicate. Last-hard-stop/generation contribute to binding; they are not independently interpreted as permission. Projection <=4096 bytes or incomplete. Hash is PostgreSQL jsonb text SHA, not Python canonical JSON digest. |
| oldham_authorities | 1 summary | Union of allowance keys and Oldham-prefixed grant names; <=32, matching counts. Compare both expiry epochs with observed_epoch; nonrevoked/unexpired allowance AND unexpired grant is potentially live. This does not evaluate the full Oldham predicate or authorise use. Allowance/grant/binding types must be object, revoked type boolean and both expiry types number. Numeric-looking JSON strings are not valid numeric expiry evidence. Missing/malformed required fields, an unmatched grant/allowance or binding mismatch is unresolved. No full grant/package/source payload exported. |
| end | 1 | Fixed readonly disposition, then ROLLBACK and normal psql exit required. |

Any SQL error, output/deadline limit, missing required row, NULL required comparison, unavailable visibility, truncation, or uncertain closure is INCOMPLETE. Legitimate NULL finished_at means an unfinished attempt; legitimate absent checkpoint remains explicitly absent. A complete readback with mismatches remains OBSERVATIONS_REQUIRE_REVIEW, never an automatic pass. The current state can change after this transaction; this is not an atomic recovery permission.

## Retained evidence and closure

3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045: Bolton 22 October capture attempt; four requests, no accepted retained capture/checkpoint, provisional publication before memory-scope closure.

e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e: Bolton stable-pipeline attempt at 038e9b13c552094682a5bae0016769d0c88b5917; manifest f151f45e1178bcab3c4e798846c292855acd6dc5ddb5da49e9b56ebf8959ecf0 reproduces the key; one request, source-contract rejection, no accepted capture/checkpoint.

Whole-controller historical closure remains UNKNOWN. Source-session closure is not outer-controller closure. No further receipt hunt is a prerequisite to presenting the supported p_closed=false recovery option.

## Subsequent actions — all INACTIVE

1. Exact-key recovery: for each of these two keys only, after separately approved current-fence/expired-lease checks and appropriate existing recovery authority, call the existing ingestion_recover_abandoned(key, observed_fence, false). Never substitute a guessed fence. p_closed=false does not assert historical closure. SOURCE_INTENT recovery produces SAFETY_BLOCKED/RECOVERED, raises/preserves a safety stop, clears owner/lease, advances the fence, and records replay not authorised. The stop reason/generation may change through ingestion_raise_stop; preserving safety does NOT mean promising byte-identical stop metadata. Read back both item/attempt transitions and the new stop binding. Do not use recovery as stop clearance or B approval.

2. Installation: use existing intake_policy.installation_script(), replacing ONLY ingestion_bolton_allowed, ingestion_register_bolton_exception and ingestion_worker_step. Explicitly approve transition from the recognised Oldham-substituted worker, rather than silently treating it as the v3 predecessor. The existing ceremony temporarily GRANTs ingestion_storage_owner membership to CURRENT_USER with INHERIT/SET, GRANTs CREATE on public to that role, SET LOCAL ROLEs to it, applies the replacements and the existing registration-function EXECUTE addition to ingestion_worker, RESET ROLEs, REVOKEs schema CREATE and the temporary membership, then COMMITs. No drop of ingestion_oldham_allowed or unrelated ACL change is proposed. Before using this ceremony, verify the supposed temporary membership/schema rights were absent and preserve their original semantics; stop if they are pre-existing. Verify all three final bodies/metadata/ACLs, the narrow worker EXECUTE change, absence of PUBLIC/unrelated EXECUTE, absence of temporary owner USAGE/SET and schema CREATE, and unchanged control/ledger data. No interim rollback or blanket PR205 merge.

3. Access: separately approve only bounded activation of the existing worker/effect route for eventual B, existing timeout/TLS checks and closure verification. No standing access, new login or capability expansion. The observed NOLOGIN state remains untouched now. Stop resolution, current source qualification, archive/publication access and one-run period approval remain distinct prerequisites; this supplement does not satisfy them.

Decision sought next: review this fixed supplement and its client binding. Production execution would require a separate explicit approval for one connection. No recovery/install/access/B action is bundled into that approval.


## Authorised disposable validation continuation

Original ZIP is preserved unchanged. A surplus trailing newline in its client
was removed to make byte-for-byte reverse substitution exact. PostgreSQL tests
reuse tests.e2e_pg_world and the existing daily-intake-pg hosted job; setup may
install retained SQL and synthetic roles in that disposable database only.
The original inspection SQL/client remain unchanged. Hosted validation evidence
is recorded in PR #206 against the exact candidate. Execution remains inactive.

SQL correction from original 03ad0a79…: expose authority/binding/revocation/expiry JSON types and accept numeric expiry observations only when the stored JSON type is number. The old text extraction could make a numeric-looking string indistinguishable from a JSON number. No authority predicate, bound, effect or recovery action is relaxed.
