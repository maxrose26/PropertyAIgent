# ADR — source-linked AH claims with retained history

Status: separate immutable claims, append-only review/relationship history, controlled validated import boundary and the three preflight amendments approved for bounded LOCAL implementation, 30 September 2026. No production migration/import or release approval.

Context: specification020's repaired executable739895df1c613e912560943a443d7a182311e26f passed its accepted bounded offline verification. Existing raw AH fields cannot carry independently scoped quantitative source evidence. The next design must retain multiple claims, corrections and disagreements without overwriting them.

Decision: use two small AH-specific relations: immutable source claims and append-only review/relationship events. Reuse existing application/site/document identities and the AHAssessment consumer contract. No general event bus or new agent. The controlling proposed first-increment contract is [specification 021](../specifications/021-ah-source-claims-first-increment.md); it narrows the earlier proposal to count/explicit tenure claims and existing-Document-only imports. Percentage context remains independently guarded, not a new storage metric in this increment.

Why: an optional claims-array payload is adequate for frozen snapshots, but review/correction history would require additional version storage and replacement/concurrency handling. The requested complete history makes a small separate structure the smallest maintainable complete solution. This supersedes the earlier snapshot-first recommendation; it does not change already-approved threshold policy.

Selection: resolve eligible applications and schemes first, then count, tenure and percentage independently before the old percentage-based whole-record winner. Keep incomparable scopes/stages separate. Require reviewed supersession; preserve alternatives. Exact, approximate, bounds, unsupported and unknown remain distinct. Retirement/specialist exclusions remain independent. No numeric qualification from legacy values alone.

First increment: additive schema design, controlled reviewed import, strict read adapter and shared consumer projection, initially with a bounded source cohort and focused migration/rollback tests. No automatic backfill/extraction activation or general review UI. Future extraction emits pending, source-linked claims; it cannot self-verify.

History: no overwrite/delete of claims or events. Correction creates a new assertion; relationship/review events preserve actor, reason and recorded time. Concurrent stale review fails rather than silently replacing another reviewer. Rollback disables new use and preserves evidence; it does not drop tables or rewrite old evaluation hashes.

Versioning: global5 unchanged locally. Following workspace confirmation, read-only Render inspection found all five identified live deployment artifacts at 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a; exact-commit source declares matching version4. This does not prove5 was never used elsewhere or historically. Supabase attachment failed before any query, so stored impact remains unknown. The history policy string does not record matching version. See specification021 section9 for service/deployment identities and measurement limits.

Local implementation approved, including three amendments: reject identical different-key imports with the canonical identity/key; permit evidenced same-source scope corrections without suppressing unrelated claims; never use unchecked stage labels to partition away disagreements. See specification021 for the controlling contract. No production operations or release are approved. Actual stored-combination measurement remains outstanding pending read-only database access.

Local approval does not authorise a production migration, production claim import, stored-result refresh, paid evaluation, push, merge, deploy, discovery resumption or P0-A changes. PostgreSQL runtime validation and measured stored impact remain separate release gates.
