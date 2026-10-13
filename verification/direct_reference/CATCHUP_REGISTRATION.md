# Stage 4 admitted policy-due catch-up registration

Preparation/registration only. No execution authority. Stage 4 remains OPEN.

The accepted full census was taken at 2026-10-13T08:49:12.508887Z, after Oldham42's accepted production canary (38370055696). Oldham42 was already fresh and is outside the census's 39 admitted policy-due records. Representative20 (38383222682) subsequently refreshed three of those39:381,409,468; safely withheld41,53,56; and safely rejected305,783 after Trafford timeouts. Stockport78 is a ninth previously attempted policy-due identity: the earlier retrieval-only run38310507094 verified its literal facts without B2 persistence or a verification stamp. It remains due but must be excluded from a previously-unattempted operation.

Therefore **39 = 3 refreshed + 3 withheld + 2 timeout + 1 previously retrieved without persistence + 30 unattempted**. The anticipated29 is not supported by the retained census and live audits. There are36 still-due records, comprising30 unattempted and6 excluded residuals. There was no new production census/query during preparation. Current-policy membership means the accepted retained policy classification reconciled with accepted outcomes; policy reclassification or subsequent external production changes are not independently surveyed.

`catchup-ledger.json` pins this reconciliation. Both manifest files contain only approved identity/source admission metadata and bounded prior factual/watermark comparison context; no raw database export, narratives or personal/contact data is retained. Every route/reference/source identifier exactly equals the existing direct admission manifest. Ordering is council code, then numeric application ID. All30 are policyA.

| Cohort | Count | Manifest | SHA256 |
|---|---:|---|---|
| A | 20 | catchup-a-manifest.json | 96afbb6eef61cd1eee6ae24d5e21a047152f61492c25edfd5d6e86dc3f315ede |
| B | 10 | catchup-b-manifest.json | 277c6b43018a03d06301f953526e99979102b851a7d62c61b29ebd9d54791760 |

A IDs:1068,24,28,29,31,32,39,40,354,390,392,393,403,106,174,58,59,60,446,290.
B IDs:309,310,317,318,342,345,572,589,597,775.

Two manual-only workflows select their own cohort through exact master workflow identity. No cohort/file/application/reference/URL selector is exposed. Authority tokens are `AUTHORISE_STAGE4_ADMITTED_CATCHUP_A_B2_ONCE` and `AUTHORISE_STAGE4_ADMITTED_CATCHUP_B_B2_ONCE`. Each workflow permits run1/attempt1 only; registration does not authorise dispatch. BatchB requires its own later REVIEW decision, exact SHA/hash/zero-run preflight, and consideration of BatchA's result. Shared concurrency prevents A/B overlap.

The accepted batch runner gains immutable reviewed manifest/registration context parameters; representative20 remains its default and its frozen contract/hash is preserved. Both catch-up cohorts use the same existing isolated worker, fresh official transport, exact-reference qualification, production route guard, B2 transaction adapter, independent bounded readback and closed audit validator. Manifest prior facts never become observations or transaction inputs: only identity is passed to the worker; B2 loads the actual prior production state before fresh retrieval. No second writer, migration, DDL or alternate watermark exists.

Record-local failures continue only after unchanged prior facts, known transaction, valid audit and successful cleanup. Uncertain commits, identity/privacy/resource/audit/cleanup failures stop. No automatic resume or second invocation is exposed by either workflow. Prior accepted reusable core resume capability is unchanged and remains separately gated.

Per invocation: maximum20 sequential records/40 GET attempts/one eligible retry per reference; zero followed redirects;1MB per response/20MB aggregate/150s cumulative source time;45s per record worker;512MiB/30CPU seconds;300s batch worker/10min outer job;one concurrent DB connection with existing timeouts;16KiB per-record/384KiB batch audit. Smaller B receives no increased limits. Secret `DATABASE_URL` is referenced only by the live transaction step in environment `stage4-production-canary`; install, offline and disposable jobs receive no production secret. Workflow permissions are contents:read; checkout credentials are not persisted.

Audit schema and privacy remain unchanged: identity, fresh provenance, field states, semantics, B2 result, transaction/before/after/watermark/lifecycle/evidence-refresh consequences, resource accounting and cleanup. No raw HTML, credentials, cookies, arbitrary headers, narratives or contacts. No models or regeneration. Existing material-change evidence-refresh flags and stale-narrative qualification remain intact. Missing decision/date NOT_PRESENT is not NULL and still withholds acceptance; unknown status mapping is unchanged. Trafford residuals receive no special retry/time allowances.

Only minimum new reconciliation, partition, fixed admission, workflow scope, orchestration and substitution tests are added; existing batch/offline/disposable regression gates remain. Production networking is denied by the accepted offline runner; native acceptance uses disposable localhost PostgreSQL only. Existing B2/transport/adapter/source supervisors are unchanged.

Accepted pilot security limitations remain: postgres-role credential; uninspected privileges/no established DB-enforced least privilege; environment approval is not an exact-workflow allowlist; previous private tool-record credential exposure accepted and unremediated; independently proved negotiated TLS/certificate/hostname verification remains incomplete. No credential value is inspected or tested in registration.

After future catch-up,619 offline-compatible unsupported applications remain an admission-extension candidate;84 census policy-due unsupported records remain separately tracked. Their overlap/admission and live reliability require later authority. Missing-field semantics, Trafford availability, factual-change→intelligence-refresh coverage, later discovery/change signals and operational safety remain Stage4 gaps. No discovery, Arcus, scheduling, Stage5, rollout or deployment follows from registration.
