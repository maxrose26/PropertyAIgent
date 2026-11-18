# PA-TAM002 v1.4 operational checkpoint and campaign ACL correction

Stage 4 OPEN. This correction is offline and is not an operational pin acceptance.

## Production evidence

Owner acceptance: issue #214 comment 6962672279. Execution claim: PR #227 comment 6962747160. Partial execution: comment 6962887945. Detailed containment and blocker: comment 6963036748.

Invocation `pa-tam002-v14-preparation-01` used executable `9524503fa90228f31d48d16a58121c45d3eb90b8` and package `65a44ec8e1be42c1a80ea1a4de63088219a14f56`.

Verified archive restoration preceded committed Bolton recovery under STOP14. Independent readback confirmed STOP15. The journal namespace was installed and a durable encrypted checkpoint preceded provider changes. Deployment `dep-dbud93o8v5cc738opj1g` reached the accepted executable. A pending-build acknowledgement was reconciled using the existing intent and stopped-deployment inspector, without repeating the resume/build. Original service settings/environment were restored and suspension confirmed. Six historical dispositions and the private writer were installed and independently read back. No campaign installation, release, activation or collection occurred.

At 2026-11-17 22:36:06Z, independent containment confirmed both stops at generation 15, worker/effect NOLOGIN, zero matching database sessions, restored temporary owner privileges, absent campaign function and Tameside registration/run, original archive integrity, exact provider/environment restoration, and terminal provider jobs/deployments. Owner-host inspection found no surviving Python/timeout processes. Receipt SHA-256: `12c902bb324a2e24fee7bdec1988933be71f67125a0b468ad58bb17f2edb9ab5`.

New journal ordinal 18: `0e6d08aa0b6e04c669998a828924e30322bab4ac73a0cf157a9d63b5fac955af`.

## Demonstrated defect and correction

The campaign installer granted EXECUTE only to postgres. The runtime requires ingestion_worker to execute that function. Production default function privileges for ingestion_storage_owner are owner-only. The joined fixture supplied an extra worker GRANT, masking this omission.

The stopped installer now grants non-grantable EXECUTE to exactly postgres and ingestion_worker. This does not enable login or relax the existing finite access lifecycle. The owner access inventory independently requires that exact ACL before access issuance. The actual-recovery joined test no longer supplies the missing privilege separately.

## Focused validation

- Regression assertion first failed against the accepted installer because the worker lacked EXECUTE.
- Corrected actual-entrypoint joined PostgreSQL test passed: recovery, stopped preparation, conditional release, synthetic capture, retention, screening, backlog and cleanup; no extra fixture worker grant. Provider/source effects simulated, not production proof.
- Initial two-test run had one passing joined test and one test assertion error (incorrect negative role name). The assertion was corrected to the existing ingestion_effect_broker role; implementation was unchanged after the joined pass.
- Final installer and package checks: 6 passed. Six IO tests initially skipped because the frozen-checkout environment variable was omitted; rerun with the exact pinned checkout: 6 passed, no skips.
- No production ACL correction, replacement deployment or collection was performed.

## Preserved finite binding and next dependency

The inactive production package has manifest SHA-256 `dd4d381be32c592bf8346172c538305662953beb259b1fe7b6d880acd2f46e54`, index `276e45cecd898b12ea1d2c427c230febbe4714d9ea32bf60ab3798ac05c73496`, bound_at `1794954750.6068778`, runtime expiry `1794956665.6068778`, access deadline `1794956850.6068778`, and latest submission bound_at + 600 seconds. These values must not silently slide or be reused with changed source.

NO-GO for production continuation on the old package. Independent REVIEW must assess the exact ACL correction and a continuation amendment from the committed STOP15 state, including its finite binding. Do not replay Bolton recovery, dispositions, writer installation or deployment merely to restart the sequence. Reconcile retained journal and independently inspect current state before any newly accepted continuation. Preserve original receipts, UNKNOWN facts and permanent no-replay. The single Tameside RECEIVED 15–21 September 2026 submission remains unused. Overall owner expiry remains 18 November 2026 20:00 London, latest binding 19:25; no automatic extension.

No new collected, retained, updated, screened, qualified, saved-fact or backlog records are demonstrated by this operation. This is not a claim about the total existing database population. All-ten Greater Manchester follow-on coverage remains outstanding, explicitly including Manchester, Bolton, Tameside and Trafford.
