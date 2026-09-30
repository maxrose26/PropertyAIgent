# AH provenance implementation preflight — blocked decisions

30 September 2026. Local implementation is authorised, subject to the user's explicit instruction to stop material design gaps for review. These are defects/ambiguities in the prepared specification, not newly authorised implementation choices.

Inspected isolated branch: `review/ah-downstream-audit`.
HEAD: `e0ad67ba3cf95b612bcf1bc42f073e5d8adfe60c` (documentation after accepted executable `739895df1c613e912560943a443d7a182311e26f`). Existing uncommitted ADR/proposal/specification files were preserved.

## 1. Duplicate import key cannot be retained

Specification021 section4 promises that a different import key with the same canonical payload returns the existing assertion. The immutable claim row has only one unique import_key; the event schema has no import-receipt action or alias storage.

Counterexample: import K1/P succeeds; K2/P returns the same claim; K2/Q later arrives. No persisted K2/P binding exists to reject the changed content. The promised changed-content rejection therefore cannot hold across all successful requests. An in-memory cache is not an acceptable fix.

Recommended bounded amendment: only the original canonical key is a successful idempotent import identity. A different-key duplicate returns a validation error `duplicate_payload_use_original_key` plus the original claim/key; it is not acknowledged as a successful import. Same key/same payload returns the original claim; same key/different payload fails. If accepting arbitrary alias keys is required, that needs a separately reviewed durable receipt design, not an improvised third table or an unrelated review event.

Required tests after approval: K1/P replay; K1/Q rejection; K2/P validation error; concurrent K1/P imports; same-key competing payloads; transaction rollback leaves no success receipt or claim.

Blocked: import contract and final storage/migration contract until this decision is agreed.

## 2. Scope correction has contradictory compatibility requirements

Section2 requires an immutable replacement plus CORRECT when resolving unclear scope or null site. Section4 requires same metric/tenure/scheme/scope compatibility for replacement links, without defining which changes CORRECT permits. A whole-scheme misattribution corrected to a named component is commercially important: disallowing it strands erroneous evidence; accepting arbitrary cross-scope links could hide valid independent claims.

Recommended bounded amendment: separate CORRECT from SUPERSEDE validation. CORRECT may fix a miscaptured quantity/qualifier or scope/site assignment of the same source assertion, supported by the identified original document/passage, an explicit correction reason and a separately accepted replacement. Do not use it to erase a different document's competing assertion. Where the source passage itself was captured incorrectly, require the reviewer to identify the original locator and corrected passage explicitly. Different source assertions remain independent unless a supported SUPERSEDE relationship applies. Scheme reassignment must be explicit, with both contexts previewed and locked; no implicit same-site reassignment. SUPERSEDE retains compatible metric, tenure, scheme and scope requirements. Metric/tenure reinterpretation beyond this narrow correction boundary remains for separate review.

Required tests: unclear-to-component; erroneous whole-scheme-to-component; null-site resolution; unrelated-source correction rejected; original history retained; stale reviews across old/new contexts rejected.

Blocked: relationship validation and selection of corrected claims.

## 3. Unchecked stage labels must not partition away disagreements

Section5 groups by planning-stage context, while the claim's planning_stage is explicitly source-reported and can be unchecked on ACCEPT. The specification does not precisely define whether/how that raw stage enters the grouping key. Grouping directly on it would allow two accepted contradictory counts for the same scheme/scope to evade conflict detection because one says proposed and another says legally_secured, even when neither stage was checked.

Recommended bounded amendment: derive planning-context identity from supported application/scheme relationships, never the raw planning_stage label alone. Within one context, accepted conflicting quantities remain alternatives regardless of unchecked stage labels. Display unchecked stage as reported/unverified. Separate proposal/consent contexts require supported context membership; ambiguous membership stays investigation. Checked stage alone still does not choose the winning count or establish availability; a supported explicit relationship must resolve applicable conflicting assertions.

Required tests: same-context conflicting counts with different unchecked stages remain conflicting; newer date does not win; source acceptance without stage acceptance remains useful but unverified as to stage; genuinely separate supported proposal/consent contexts remain distinct.

Blocked: selector, shared projection and dependent consumer integration.

## Other preflight findings

- Existing Document.content_hash is a whitespace-normalised extracted-text hash, NOT a PDF-byte hash (`app/db/models.py`, Document). Never copy it into the proposed document_content_hash byte-hash field. Capture a raw extracted-text hash with the prescribed convention where available; leave byte hash absent unless actual bytes were hashed. No source fetching or backfill is authorised.
- Existing AHClaim.threshold permits a supported component above a maximum to establish nonqualification, while refusing to use a small component to prove whole-scheme maximum compliance. This does not assert a whole-scheme total or upper bound. Preserve that distinction; do not silently change accepted spec020 policy.
- Acceptance is a source/scope review, not proof of legal security, current status or availability. Independent specialist exclusions and no-write/no-paid-read behaviour remain mandatory.

## Work stopped and evidence status

The gaps span import identity, relationship history and selection. Building a partial migration now would freeze an unresolved contract; consumer wiring depends on the unresolved selector. No executable code or schema was changed. No disposable database or test run was started. No new tested SHA, failures/skips or candidate/baseline comparison is claimed. Prior accepted results remain historical evidence only.

Only this preflight report was added this turn. No production connection, migration, import, write, refresh, paid call, push, merge, deployment, discovery resumption or P0-A change occurred. Local matching-policy constant remains5; production version4 findings were not remeasured. Actual stored combinations and real-source acceptance remain separate uncompleted release gates.

Resolution: the Product Owner subsequently approved all three narrow amendments and continued bounded local implementation. Specification021 now records the approved semantics and local implementation boundaries. The stopped-work status above records the earlier preflight checkpoint, not the subsequent implementation state. No dashboard, extraction, percentage storage or contact-data scope was added.
