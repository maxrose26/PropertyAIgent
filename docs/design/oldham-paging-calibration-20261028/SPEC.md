# Oldham paging calibration (dormant; inactive until the owner approves its exact registration hash)

Stacked on the response diagnostic (`oldham-response-diagnostic-20261028`). Stage 4 remains OPEN. No parser, proof or completeness classification is changed by this tool.

## Why
The 2026-10-28 diagnostic found no count or navigation signal in the **inspected places** of the Oldham single-page response (it did not examine the results subtree, external scripts, the rendered DOM, headers or wording outside
its patterns). Completeness for a single-page Oldham result therefore stays UNKNOWN. Whether the portal's own paging can establish *terminal* pagination without a displayed total has not been tested. Before any rule is applied to a
single-page window, the paging behaviour is calibrated on a result that does show an explicit total.

## Existing paging mechanics (read from the reviewed code, not assumed)
* The date search POSTs to `advancedSearchResults.do?action=firstPage`; the reader then POSTs the `form#searchResults` sort form (`orderBy=Reference`, `orderByDirection=Descending`, `resultsPerPage=10`, hidden `_csrf`,
  `searchCriteria.page`, `action`) to `pagedSearchResults.do`. The hidden `searchCriteria.page` in that form is the **current** page (observed `1`), not a request for another page.
* Further pages are GET links the portal itself offers in `p.pager a.next`: `pagedSearchResults.do?action=page&searchCriteria.page=N`. The parser accepts a link only if N equals the current ordinal + 1, and a page only if its
  `Showing a-b of T` marker has `a = (ordinal-1)*size + 1` and `b-a+1 = rows`. That is how `page=2` is known to be rows 11..: it is verified on every accepted multi-page window (Oldham 14, Tameside 15, Stockport 49), not guessed.
* Session continuity is the HTTP session cookie plus the server-side search state; the sort must show Reference/Descending selected on every page (`require_reference_sort`). No token is needed on the GET links.
* Nothing in the repository covers a page **after** the last. The reader never constructs a page URL; this tool builds exactly one, in the portal's own link shape.

## The calibration (one session, at most 8 requests)
form, date search (Oldham RECEIVED 2026-10-08..21), sort, each next-page link the portal offers up to the explicit last page, ONE request for page P+1, a refine-view request (session and criteria still alive), and ONE
invalid-page control (`searchCriteria.page=0`). It stops with no beyond-the-end request unless the result has an explicit total of 11..30 on 2..3 pages. Limits are the existing reader's own (500,000 bytes per response, 3,000,000
combined, 45 s) plus the diagnostic's 3 s / 8 s dispatch, 50 s supervisor and 120 s scope. Raw bodies are private (0700/0600); the export is hashes, sizes, statuses, counts and structural fingerprints.

## Predeclared classification (`classify`, fixed before any live response is seen)
ESTABLISHED requires **all** of: every page via the portal's links with the marker arithmetic above and a constant total; no repeated rows; the sort shown on every page; the last page explicit (`last = total`, no next link) and the
union of rows equal to the total; the beyond-the-end response HTTP 200 `text/html`, no redirect, zero rows, no overlap with any earlier page, not a repeat of any earlier page, a results-page heading, and one of two specific shapes
(an explicit `Showing ... of T` marker with `T` equal to the observed total, or a message matching `no more|further results` / `end of results`); the session-check refine view echoing both requested dates; and an invalid-page
control that is neither the same shape nor a specific exhaustion shape. CONTRADICTED: rows beyond the portal's own total. Everything else, including a repeated or clamped page, an ignored page parameter, a redirect or error, a login or
generic page, an empty container with no marker, or a failed step, is INCONCLUSIVE. A shape not listed above is never accepted after the fact; a new rule needs its own review.

## What a successful calibration would and would not prove
Proves, for that session and that day: the portal advances correctly on its own links, and answers a request for the page after the last with a specific, session-alive response that an invalid request does not produce.
Does not prove: the same response for a result that fits on one page (page 1 then had no pager), stability over time, other councils, or completeness of any window. A separately approved application to the single-page window,
read against the same rule, would still be needed, and no production classification changes until that is reviewed.
