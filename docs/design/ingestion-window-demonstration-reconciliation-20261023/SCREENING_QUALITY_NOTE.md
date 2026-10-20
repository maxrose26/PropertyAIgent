# Screening-quality note: "insufficient evidence" versus "known size outside the current target"

Status: **documentation and a proposal only. No screening behaviour is changed by this note or by the accompanying candidate.** Historical results are preserved.

## 1. The case
Bolton reference **01757/26** (item 24 of the 24 captured schemes): "ERECTION OF TWO STOREY RESIDENTIAL BUILDING COMPRISING 6 SELF CONTAINED FLATS".
* **Recorded:** the archived run records the aggregate only (20 `INSUFFICIENT_EVIDENCE`); the recorded per-reference outcome for this scheme is not in the archive.
* **Local recomputation** (same pure function, rule `manchester-listing-screen-assessment-v1`): disposition `INSUFFICIENT_EVIDENCE`; existing classification `Ignore - under 10 units`; category `primary_residential`; extracted unit count **6**.

## 2. The defect in meaning
The listing text states a **known size** (6 flats). The existing qualifier recognises it and classifies the scheme as below its 10-unit threshold. `screen_row` then has no branch for "known size below the threshold": every classification that is not qualifying, related, or one of three named exclusions falls into the final `else` and is labelled `INSUFFICIENT_EVIDENCE`. The label therefore says *we lack evidence* for a scheme where we have exactly the evidence needed to say *it is a known 6-unit scheme below the screening threshold*. Two different facts share one label:
* **Insufficient evidence:** size/use cannot be established from the listing (unusable text, ambiguous size, truncated).
* **Known size outside the current target:** size established and below the target.
Conflating them hides a positive finding (a verified small scheme) behind a gap, and would mislead any consumer that reads the disposition alone.

## 3. What "the current target" is today (existing buyer criteria)
* The qualifier's own purpose: "plausibly 10+ unit residential schemes" (`app/scrapers/unit_filter.py`), default `unit_threshold = 10`.
* Per council, `config/councils.yaml` carries `unit_threshold` (10 for the councils configured there); the weekly pipeline passes it to `qualify`.
* **`screen_row` ignores the council setting** and calls `qualify(text)` with the module default 10. For Bolton the value coincides, so nothing differs today, but the listing screen is not bound to the configured criteria.
* Buyer mandates (specifications 024/027/028) express buyer-specific interpretation separately; the listing screen has no buyer context (`commercial_relevance` is always `UNKNOWN`). So "outside the current target" can only mean *below the screening threshold in force*, **not** "unsuitable for any buyer". A 6-flat scheme may suit other buyers; it must remain retained and `permanent_exclusion = false`.

## 4. Smallest proposed correction (not implemented)
**Option B (recommended first): additive fields, no new outcome string.** Under a new rule version (`manchester-listing-screen-assessment-v2`), when the proposal is usable, residential wording is present, the existing qualifier returns a **known unit count** below the threshold used, and the scheme is not a related-application lead, `screen_row` adds:
`size_assessment = KNOWN_BELOW_SCREENING_THRESHOLD`, `known_unit_count`, `screening_threshold` (the value actually used), and a fixed `reason` code. The disposition string is **unchanged**. Everything else is byte-identical. No grant `completion_outcomes` list, database function, registration or owner binding changes (those enumerate allowed disposition strings; see `operational_owner.register`).
**Option A (later, needs owner/grant changes): a distinct disposition** `KNOWN_SIZE_BELOW_SCREENING_THRESHOLD`, which requires adding the string to the `SCREENING` completion outcomes in the grant, hence a reviewed owner change and a new registration binding; do this only after Option B is accepted and downstream consumers read the field.
**Both options:** source the threshold from the council configuration instead of the default (a separate, smaller correctness fix); keep `INSUFFICIENT_EVIDENCE` for unknown or ambiguous size; guard against non-dwelling "units" (item 1, "1 NO. AIR HANDLING UNIT", yields a unit count of 1 from the generic pattern and must not be reported as a known 1-unit residential scheme: the residential-wording condition excludes it).

## 5. Effect on the 24 schemes (local recomputation, not recorded results)
Only one record changes under Option B: **01757/26 (6 flats)** would add `size_assessment = KNOWN_BELOW_SCREENING_THRESHOLD, known_unit_count = 6, screening_threshold = 10`. Item 1 (01797/26) has a count of 1 but no residential wording, so it stays unchanged; item 16 (49 apartments) is unchanged (`SUPPORTED_PROCESSING_PRIORITY`). The other 21 records have no extracted unit count and are unchanged.

## 6. Historical results
* Every stored result carries `rule_version`; v1 results are **not rewritten, deleted or reinterpreted**.
* A v2 result would be a new result under its own rule version (the child item identity today depends on the record digest only, so re-screening existing items under v2 needs an explicit decision on item versioning; none is made here).
* The aggregate of the 20 October window (1 / 3 / 20) remains a statement about v1.

## 7. Decisions needed before any change
1. Option B first, or B and A together. 2. Whether the screen should read the council `unit_threshold`. 3. Whether and how existing items are re-screened under v2 (new item versions vs prospective only).
