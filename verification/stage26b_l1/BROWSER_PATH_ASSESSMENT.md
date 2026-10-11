# Oldham Idox browser-path reuse assessment

Date: 11 October 2026 (UTC).
Inspected integration base: `f876b50a925cb8485750aef7a3815872ade6e7c2`.

Decision: **NO-GO — EXISTING BROWSER PATH CANNOT BE SAFELY BOUNDED**
for the presently proposed canary. This is a readiness finding, not a claim
that browser enforcement is fundamentally impossible.

## Scope and source evidence

No council request, application/database import for evaluation, deployment,
live workflow dispatch, persistence or compatibility correction was performed.
The failed raw-HTTP approaches remain historical evidence, unchanged.

The exact existing `app/scrapers/idox_portal.py` was inspected, especially
`fetch_application_by_reference`, `_goto_with_retry`, `fetch_application_detail`,
`extract_table_fields`, and `search_related_applications`.

The existing exact-reference helper navigates to `council.search_url`, fills
`searchCriteria.reference`, clicks the Search control and waits for networkidle.
This genuinely reuses browser form behaviour without reconstructing its fields.
It does not require the generic related-application search.

However, that helper cannot be called unchanged for the status-only canary:

* Results fallback collects application key values and selects
  `sorted(keyvals)[0]`; multiple candidates do not fail closed.
* A key in the current URL is accepted without independently checking the
  displayed detail reference against the authorised reference.
* It switches to Requests-based summary retrieval, proposal qualification and
  further-information retrieval, including fields outside the status-only scope.
* Its navigation helper permits three attempts; Requests has its own retry
  budget. These are not the canary's single permitted transient retry budget.
* There is no run-wide browser request admission, byte budget or exact
  two-reference allowlist in this generic helper.

`extract_table_fields` is a reusable pure table parser, not a status-only
validator. Additional reference equality, required-field and contradiction
checks would still be required. Missing dates must remain missing; absence of
results cannot establish REFERENCE_NOT_FOUND without completeness evidence.

## Smallest prospective reuse boundary — not implemented

The browser form interaction and pure table parser are potential reuse points.
A verification-specific caller would need to reject ambiguity/pagination,
confirm the detail reference, accept only summary status/decision/date fields,
and deny documents, further-information/contacts, related/history traversal,
downloads, popups and unapproved origins before issuing requests.

This is not an approved implementation design. The whole generic helper cannot
be treated as a safe wrapper target just because its initial form interaction
matches the desired behaviour. No second browser scraper or replacement
transport was created.

## Request and byte accounting

A context-level interception policy could count admitted requests (including
redirects/retries) and block unneeded assets, XHR and external origins. Service
workers would need blocking and all pages would need coverage. A page-only
navigation counter would be insufficient. Twenty total requests and ten per
reference remain unchanged. No fixture or live evidence establishes that the
actual Oldham browser path fits those budgets; no normal asset set is asserted.

The installed Playwright implementation was inspected in `_impl/_network.py`:
`Response.body()` returns a complete decoded body; `Request.sizes()` requests
size information from the response; `Route.fetch()` uses the API request
context. These inspected APIs do not establish an enforceable streaming cap on
normal browser receiving. Checking `Content-Length` or rejecting an already
buffered body is not proof of the accepted hard receiving ceilings. Encoded
transfer sizes must not be silently equated with decoded response-body bytes.

No existing inspected wrapper proves the 2,000,000-byte per-response and
10,000,000-byte run-wide boundary for HTML/XHR/browser traffic. Download denial
alone does not solve this. CDP/streaming or proxy alternatives have not been
implemented or proved and are not automatically authorised. This assessment
does not claim those alternatives are impossible.

## Runtime and rehearsal evidence

The repository already has a GitHub-hosted `ubuntu-24.04` browser acceptance
workflow (`.github/workflows/b21-rendered.yml`) that installs Playwright 1.55.0
and Chromium dependencies. This supports dependency availability as an existing
repository pattern, not Oldham canary acceptance.

The attempted local Playwright startup failed before browser launch with
`PermissionError` executing the installed Playwright driver `node` binary.
The permission restriction was not bypassed. No council network request was
made. Actual browser fixture rehearsal: **NOT COMPLETED**. Hosted offline
browser rehearsal: **NOT RUN**. No browser-request counts, measured body-byte
enforcement, browser deadline or browser cleanup proof are claimed.

The accepted disposable Actions runner remains the final process-cleanup
boundary. Existing independent supervisor/job deadlines are reusable concepts,
not proof that this unimplemented browser path is ready. No shared Render
process engineering was resumed, and no OS-level egress isolation is claimed.

## Preservation, privacy and independent review

No generic Idox file, registered workflow, verifier allowlist or raw-HTTP path
was changed. This candidate is assessment documentation only; it neither
registers nor launches another council-access path. No HTML, screenshots,
cookies, storage, tokens, values, personal data or production evidence are
included. Failsworth refusal and Southlink pending remain prospective fixture
expectations, not newly verified council facts.

A fresh independent reviewer inspected the actual generic helper and installed
Playwright API source. The reviewer confirmed first-result selection, absent
detail-reference equality, raw-HTTP/further-information continuation and retry
mismatch. The reviewer agreed that byte enforcement is unproved, not impossible,
and that fake-page tests could not substitute for actual/hosted browser
networking and cleanup proof. Independent recommendation: NO-GO.

## Review gate

No live authority is requested. Return to Product Owner priority reassessment.
The commercial need for freshness remains; it does not justify relaxing
ambiguity, request, byte or privacy limits. Do not automatically build another
access architecture, retry metadata/raw HTTP, dispatch a canary, or poll the
211-reference manifest. A different bounded scope would require a new explicit
REVIEW decision.
