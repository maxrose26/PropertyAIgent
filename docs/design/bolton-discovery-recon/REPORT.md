# Bolton Idox fixed-date discovery reconnaissance preflight

Recommendation: **GO — BOLTON DISCOVERY RECONNAISSANCE READY**, subject to the
exact remote candidate passing hosted offline CI and independent review. This
means safe preparation for REVIEW to consider registration and one live dispatch.
Neither registration nor live execution is authorised here. Successful Bolton
form/result compatibility is UNKNOWN until that experiment; qualified failure is
an honest reconnaissance outcome, not permission to patch and retry.

Base: `da06dae001cbef9af6c0f38776e1fa4adfb022b3`. PR #52 and its accepted synthetic
package remain unchanged and unmerged. This branch does not extend that synthetic
family state machine. No production scraper, classifier, DA0 model or application
logic changes are included.

## Fixed experiment

Bolton only, NEW_APPLICATION_DISCOVERY, RECEIVED date **19 February 2026 to
19 February 2026 inclusive**. The retained October8 source table for00307/26
records `Application Received = Thu 19 Feb 2026`, while validation was23Apr2026.
The minimised historical projection and original retained-file SHA256 are in
`date-evidence.json`. This is date-selection evidence, not a current lookup target,
result-count guarantee, or council truth certification. No reference is submitted.
The narrowest calendar window is selected; no volume maximisation or adaptive
window expansion exists. The run stops if the day has multiple pages.

Existing `app/config.py` supplies the received-field names and Bolton origin;
`app/pipeline/run_weekly.py` supplies existing day/month/year input convention.
Existing Idox verification code represents `advancedSearchResults.do?action=firstPage`
and `search.do` submission route shapes. Their acceptance here is a restrictive
experiment contract, not proof that current Bolton will use/accept either.

## Two-operation HTTP contract

1. GET exactly `https://paplanning.bolton.gov.uk/online-applications/search.do?action=advanced&searchType=Application`.
2. POST only to the selected same-origin form's exact admitted action:
   `/online-applications/advancedSearchResults.do?action=firstPage` or
   `/online-applications/search.do`.

No third operation. Requests session has trust_env=false (no proxy/netrc inheritance),
no authentication, retries=0, redirects=false, TLS verification unchanged, and
Accept-Encoding:identity. Session cookies, if received, remain ephemeral and only
serve these same-origin operations. They are never exported. No cookie/header
experimentation or browser/session credentials exist.

The same Requests transport is tested with its send operation mocked. URL/method/
payload admission precedes dispatch; attempts count before sending. Responses
stream through raw reads with decoding disabled, bounded chunks and raw tell()
accounting in finally. Failed and partial bodies count. Non-200 bodies are bounded
and counted before failure. Redirects are observed/countable but never followed.
Attachments or unsupported compression are rejected before consuming their bodies.
No Content-Length trust. Counters measure response-body octets consumed by the
HTTP client, not TLS/header/TCP traffic or unread bytes in operating-system buffers.

## Form classification and submission

Select exactly one form containing both exact received-date input names. Require
POST, URL-encoded form encoding, admitted action, closed document/form, no duplicate
attributes, no nested forms, no external associated controls, target/base element,
or per-control action/method/encoding override. Maximum80 controls.

| Category | Rule |
|---|---|
| APPROVED_DATE_INPUT | Both exact received-date text inputs must be enabled, writable and initially empty. Submit19/02/2026 for both. |
| REQUIRED_SERVER_STATE | Only existing recognised CSRF/Struts token identities `_csrf`, `csrfToken`, `org.apache.struts.taglib.html.TOKEN`, hidden type, unique name, bounded token-shaped value, selected-form binding. |
| APPROVED_FIXED_SUBMIT_CONTROL | Exactly one Search submit control; unnamed or name=action. Only action=Search is transmitted if named. |
| IGNORABLE_CONTROL | Disabled, reset/button, unchecked checkbox/radio, or empty optional control; omitted from payload. |
| PROHIBITED_SEARCH_EXPANSION | Any other populated searchCriteria/date control rejects before POST. |
| UNKNOWN | Populated unclassified state/control rejects before POST. |

The state category denotes structurally admitted anti-CSRF state, not proof that
Bolton requires that token. Presence alone does not qualify arbitrary hidden
fields. Values are never logged/exported; transport revalidates payload names and
fixed dates. No reference, address, postcode, applicant, proposal, decision or
other criterion is populated. Unknown defaults (including nonempty "All" values)
remain rejected until separately evidenced; they are not guessed harmless.

## Result contract

This tests first-response discovery mechanics, not full-window completeness.
Conservative proposed parser expectations:

- a unique `#searchresults` container;
- nonempty `li.searchresult` rows, maximum20;
- admitted application summary links, inspected but never fetched;
- exact `Ref. No:` values from `.metaInfo` when available; missing reference stays null;
- same-key duplicate links within one row reconcile only if their displayed references agree; duplicate keys across result rows fail closed;
- optional structurally parsed `.searchinfo` source count;
- pagination observed from next/pagination links or an explicit remaining count.

Zero requires the results container plus explicit `.noResults`, the narrow zero
message, no rows/links and no pagination. Generic "No results" text is insufficient.
Form returned instead of results becomes FORM_REJECTED. Unknown structures produce
LAYOUT_UNRECOGNISED or another conservative failure. These selectors/labels are
recognition hypotheses exercised offline, not claims about current Bolton markup.

PAGINATION_PRESENT is recorded and stops traversal before page2. Even a recognised
single page is FIRST_RESPONSE_ONLY_COMPLETENESS_UNPROVED. Submitting fixed criteria
does not independently prove the council applied every filter. No checkpoint,
application/site creation or DA0 factual acceptance occurs.

## Output and resource limits

Closed compact JSON: manifest, repository/code/workflow identity, UTC time,
offline/live mode, fixed council/window/basis, outcome/reason, accounting and HTTP
status codes, value-free form classifications, first-response result metadata,
cleanup and budget state. Only reference/key/admitted summary path leave the
result parser. Token-like or unknown field names are redacted; arbitrary values,
HTML, proposals, addresses, status/decision facts, headers, cookies and exceptions
are excluded. Validation rejects extra fields and contradictory success metadata.

| Limit | Fixed ceiling |
|---|---:|
| Requests | 2 total, concurrency1 |
| Followed redirects / retries | 0 / 0 |
| Response-body bytes | 500,000 each |
| Whole-run body bytes | 1,000,000 including failures |
| Connection / read timeout | 3s / 8s |
| Independent worker | <=30s |
| Outer job | 2 minutes |
| Structured audit | <=32,768 bytes |
| Result candidates | <=20, otherwise fail with no partial candidates |
| Followed result pages | First response only |

One overflow-detection byte may be consumed to prove a body exceeds the ceiling;
that attempt is a failure and the byte is counted. No larger successful response
is accepted. Resource values are rejection ceilings, not measured council capacity.

## Runtime, cleanup and workflow

Manual-only prepared `.github/workflows/bolton-discovery-recon.yml`, GitHub-hosted
ubuntu-24.04, contents:read, persist-credentials:false, no environment/secrets block,
no push/PR/schedule live trigger. Only inputs: reviewed SHA, offline/live mode and
fixed authority string. No council/date/reference/URL input. SHA must equal workflow
revision and a clean checkout. Rerun attempts are rejected. Runtime checks hosted
runner, manual event, repository, first attempt and SHA. Authority string:
`AUTHORISE_BOLTON_RECEIVED_2026_02_19_ONLY`.

A future single-use decision also requires operator pre-dispatch verification of
zero prior live executions. A public acknowledgement string is not a secret or
an automated reusable authority ledger. Multiple fresh dispatches are not prevented
by the string itself. No such dispatch or default-branch registration occurs now.

Worker receives a minimal environment via env-i; no DB, Render, model or application
credentials. Minimal dependencies are an exact subset of the existing lock.
A parent process independently waits at most30s, terminates then kills/reaps its
owned worker on timeout; stdout/stderr are discarded. A temporary audit is validated
and bounded before export, and temporary directory is removed on exit. Child HTTP
connections terminate with the worker; disposable runner teardown is the final
process boundary, not a claim of hostile descendant containment. The pinned-code
admission uses short-lived git commands before HTTP work; no browser is launched.
On forced interruption, request/byte totals are UNKNOWN (null), never invented zero,
and the artifact records TIMEOUT with accounting_complete=false. Such output is
failure evidence only. Partial result metadata is not promoted to success.

## Offline validation and interpretation

Fixtures are explicitly synthetic. The real Requests preparation/streaming path
runs under a mocked send boundary; socket connection/DNS attempts are denied.
Tests cover date and payload admission, state-value suppression, field/attribute
ambiguity, origin/action/query rejection, no detail traversal, real result/zero
recognition rules, pagination stop, HTTP failures, partial-body accounting, byte
limits, timeout, artifact validation/privacy, workflow restrictions and native
worker termination with an unrelated control process surviving.

No application/database/model/browser module is imported. Generic Idox remains
unchanged. Existing offline CI runs tests and this exact launcher in OFFLINE_ONLY
mode; no live workflow is registered or dispatched. Hosted results and independent
exact-candidate review are recorded in the PR and final return.

## Next decision and strategic stop

If exact-candidate review/CI passes, request **registration-only approval first**.
After registration, a separate single-use live authority may permit precisely the
GET+POST above. It must verify exact master/workflow blobs and no prior live runs.
No page2, third request, redirect, retry or other council is requested.

If the later experiment cannot establish basic form submission and a recognised
bounded first response, return the actual failure to REVIEW. Do not automatically
patch/retry or restart platform-family engineering. Review should reassess the
commercial case for further Idox acquisition investment against provider/official
feed alternatives, rather than treating more safety tooling as freshness value.

## Independent-review correction

Review of the first published checkpoint identified two audit-validation gaps.
Success now requires the admitted POST action, both fixed date controls and the
single approved Search control. Source counts must reconcile with returned rows
and pagination qualification. Duplicate result rows fail closed. No request scope
or resource limit changed. Local focused validation: 151 passed (57 DA0 and 94
reconnaissance tests); hosted exact-candidate results remain recorded in PR #53.
