# Oldham single-page count-signal probe (dormant; inactive until the owner approves its exact registration hash)

Stacked on the paging calibration (PR #198) and the response diagnostic (PR #197). Stage 4 remains OPEN. No parser, proof or completeness classification is changed, and the evidence is diagnostic: never a registered collection audit.

## Question
The calibration (ESTABLISHED, 2026-10-28) showed that on a two-page Oldham result the page after the last answers with an empty-range `Showing a - b of T` marker whose total equals the portal's total. Whether the portal states its
total when page 2 is requested for a SINGLE-PAGE search (page 1 showed no pager and no total) is unknown, and only the target shape can answer it.

## Sequence (one fresh session, at most six requests; nothing is reused from a consumed session)
1. GET the search form. 2. POST the exact date search (Oldham RECEIVED, 2026-10-15..21). 3. POST the sort (page 1; no pager, no next link expected, sort retained, unique records).
4. ONE GET for page 2 in the portal's own link shape (`action=page&searchCriteria.page=2`), built because no next link exists on a single page. 5. GET the refine view: both requested dates echoed in the same session.
6. The MANDATORY invalid-page control (`searchCriteria.page=0`). No retry, no followed redirect, no replacement. Ceilings are the calibration's (the existing reader's): 500,000 bytes per response, 3,000,000 combined, 45 s reader,
3 s / 8 s dispatch, 50 s supervisor, 120 s outer scope, 1 GiB / swap 0; only the request cap is lowered to 6. If page 1 shows any pager or total, the run stops after request 3.

## Predeclared classification (`classify_probe`, fixed before any live response)
ESTABLISHED (the page-2 signal) requires all of: page 1 recognised, correctly sorted, unique records and the single-page shape (never asserted complete); page 2 HTTP 200 `text/html`, no redirect, recognised results heading, one container,
ZERO rows, no overlap with or repeat of page 1, and one explicit marker FOR page 2 (`first` = 11) describing an empty range; marker total equal to the number of unique records seen on page 1; the refine view echoing both dates in the same
session; the invalid-page control a response that is neither the same shape nor any explicit results-page marker; complete accounting (no retries, no followed redirects, no exhausted bound).
UNRECONCILED: a well-formed marker whose total is greater or smaller than the records seen. It means those records do not reconcile with that total; the cause (changed result set, reader defect, portal inconsistency) is undetermined.
INCONCLUSIVE: everything else, including a missing, malformed or not-for-page-2 marker, a repeated or clamped page, an ignored parameter, a redirect, an error, a lost session, an ambiguous shape, an absent or failed control.
The original five records enter the registration only as hashes (identity and metadata) and are compared, never forced: any difference is reported as drift and the historical observation is WITHHELD; the verdict itself depends only on the page-1
records actually seen.

## Private evidence
Raw bodies stay in the owner-local private directory (0700/0600). The export holds hashes, sizes, statuses, counts, booleans and structural fingerprints: no record text, reference, key, cookie or token.

## What success would and would not support
ESTABLISHED would show that, for that session and day, the portal states an explicit total for a single-page result that reconciles with the records seen. The smallest subsequent change it would support (NOT made here): in the Idox reader, when page 1 has
no pager and no next link, perform the same single page-2 request in the same session, parse the empty-range marker, and record the total as a new, separately named enumeration evidence; in the contract/proof, accept that evidence only
when the marker is for page 2, the total equals the unique records seen, and the criteria echo holds; keep UNKNOWN otherwise. It would still need review, tests, a registered collection run with release-supervisor evidence and its own approval.
It would not prove stability over time, other councils, or completeness of any window by itself.
