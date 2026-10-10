# L1 disposable Actions canary — OFFLINE preflight

Live authority: **HOLD**. No council requests, factual acceptance, database use,
bootstrap, deployment, or production policy installation is authorised here.
Prior PR #39 and native ownership NO-GO evidence remain unchanged.

## Narrow execution path

Manual `l1-oldham-canary.yml` → exact clean SHA → `actions_runner` → fresh
credential-free child → `actions_canary` → opt-in Idox
`fetch_application_status_by_reference` → existing `extract_table_fields` →
accepted L1 `assess` and canonical date/material-state interpretation.

This is HTTP-only, not a browser. Standard exact-reference HTML forms are
submitted through the accounted transport. No JavaScript, static resources,
browser descendants, further-information tabs, documents, or related cases are
loaded. Unsupported/JS-only forms return a conservative failure. This offline
design does not establish current Oldham compatibility or council truth.
Existing generic Idox function bodies and Arcus are unchanged.

Fixed reviewed baselines (date granularity, not invented times):

| Reference | Site / application | Stored baseline | Successful verification |
| --- | --- | --- | --- |
| FUL/355686/26 | 28 / 42 | Awaiting decision; no decision/date | 18 September 2026 |
| FUL/355201/25 | 25 / 29 | Awaiting decision; no decision/date | 10 September 2026 |

Failsworth's retained contradiction is refusal issued 25 September 2026; it is
not a forced live outcome. Fixtures are **MOCKED EXPECTATIONS**, not council
evidence. Actual authorised live results must be reported honestly.

## Transport and safety

- HTTPS origin exactly `planningpa.oldham.gov.uk`, standard port, prefix
  `/online-applications`; only advanced exact search, results firstPage and one
  uniquely selected summary route. All physical dispatches are accounted.
- Exact references fixed in code; duplicate keys/matches/status labels rejected;
  no first-result selection. Zero results remain PARTIAL_RETRIEVAL until source
  completeness can establish REFERENCE_NOT_FOUND (not implemented by guessing).
- Search form fields limited to the exact reference, empty additional criteria,
  fixed action/search type, and explicitly named bounded public CSRF nonces.
  Unknown fields, origins, routes, redirects, documents and assets fail closed.
- 20 total / 10 per-reference requests; sequential. One transient retry per
  reference, no automatic urllib3 retries, at most two redirects per reference.
  Redirect/retry requests count against the same ceilings. Two qualifying host
  transport failures open the run-local breaker. Parser/ambiguity failures stop
  subsequent dispatch and leave the second reference explicitly not attempted.
- 10,000,000 total / 2,000,000 per-response body bytes. Charge the greater of
  decoded bytes and exposed encoded body position; Content-Length is not trusted.
  Headers/TLS traffic are not included. Decompression cannot bypass body limits.
- 15s maximum individual transport timeout; independently supervised worker
  deadline defaults to **120s**, never more than 165s. Budget's cooperative
  deadline remains secondary. 3min outer Actions job includes setup; reserve 20s
  cleanup/upload from the recorded first-step start, reducing worker time if
  necessary. Ordinary cleanup uses SIGTERM then SIGKILL only on the owned group,
  without reaping its leader before final signalling.
- No hostile-detachment containment claim. A standard `ubuntu-24.04` hosted job
  is a fresh VM, unlike shared Render. VM decommissioning is final cleanup.
  GitHub job cancellation/upload/disposal latency is not an exact server-time
  guarantee. Cancellation before upload means unavailable audit, never success.
- Sessions/responses closed; worker temporary HOME/TMPDIR removed. No stdout/
  stderr pipes that detached descendants could hold open. No background service.

Application-level route enforcement is **not OS-level egress isolation**.
Offline mode additionally denies socket/DNS/Requests entry points. Neither path
imports production DB connectivity or model clients. Canonical helpers import
inert ORM model definitions; that is not a database session/connection. The
import fence denies `app.db.session`, provisioning, Supabase/drivers and model
clients; the fresh worker does not receive any service/GitHub credentials.

## Workflow/provenance

Manual-only trigger, no production environment, no secrets expressions/inherit,
contents:read token; checkout does not persist credentials. The canary child gets
only a new HOME/TMPDIR, fixed PATH/locale and Python safety flags. GitHub's platform
token remains available to trusted checkout/upload actions, **not** to the child.
Authority acknowledgement is an operational guard, not a cryptographic approval.
Exact SHA must equal workflow revision and clean checked-out HEAD.

The separate existing L1 **offline acceptance** workflow may run on PRs; it runs
the exact runner in OFFLINE mode, with socket denial and synthetic fixtures. It
cannot dispatch this manual live workflow. The canary itself has no push/PR hook.
GitHub requires manual workflow registration on the default branch: a separate
REVIEW-approved merge/registration gate is required before live dispatch. No
merge or dispatch is authorised by this preflight.

## Audit boundary

Compact, stable-key JSON, **16,384 bytes hard maximum**, one record per fixed
reference. Manifest/workflow version, repo/SHA, UTC time/mode/status, normalized
fact/date, sanitized summary URL, source qualification and request/redirect/
retry/byte/time/budget controls only. No raw HTML, nonce, cookie, headers, private
data or exception text. Failure artifact never labelled COMPLETE; interrupted
accounting is explicitly unknown. Artifact retention seven days. No persistence
or verification timestamp/lifecycle/intelligence update.

## Remaining gates

Exact remote candidate tests and hosted OFFLINE runner evidence; fresh independent
review; then explicit REVIEW decision for registration/merge and a separate
two-reference live authority. No Arcus completion or full 211-reference run.
