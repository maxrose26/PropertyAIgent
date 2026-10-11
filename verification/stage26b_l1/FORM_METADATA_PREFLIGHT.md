# Oldham form metadata diagnostic — offline preparation

## Purpose and certainty

Run 38121984420 failed before reference submission with `unapproved form field`.
The exact field and whether its name or value caused rejection remain UNKNOWN.
This diagnostic observes form structure; it does not guess or amend the verifier
allowlist. Fixtures are SYNTHETIC expectations, not retained/live council truth.

Base: `1e1159fa85058d71da8a9b9c555c8071a5055fc2`.
The consumed two-reference authority remains consumed. This candidate has no merge
or live authority. Default-branch registration requires a separate decision.

## Fixed transport and runtime

Manual-only `.github/workflows/oldham-form-metadata.yml`, disposable GitHub-hosted
ubuntu-24.04, contents:read, checkout persist-credentials:false, no secrets or
production environment. SHA admission compares the explicit reviewed SHA with
github.workflow_sha and the clean checkout HEAD. No council/reference/URL inputs.
Live acknowledgement is distinct: `AUTHORISE_ONE_OLDHAM_FORM_GET_ONLY`.

The only admitted request is ONE GET to:
`https://planningpa.oldham.gov.uk/online-applications/search.do?action=advanced&searchType=Application`.
No POST, reference query, second request, redirect, retry or link/resource loading.
Requests uses trust_env:false, max_retries:0, allow_redirects:false, stream:true,
15-second request timeout. A 3xx is a failure without following Location.
Actual streamed decompressed bytes and wire bytes where exposed are accounted;
the larger measure is guarded at 2,000,000 bytes. No Content-Length reliance.
A read chunk can cross the guard; that is failure, not partial success.

The accepted disposable Actions supervisor runs a short-lived child with an
independent wait timeout <=30 seconds. Ordinary group termination/forced cleanup
are reused, not redesigned. Three-minute job timeout and runner disposal are the
outer/final boundary. This is NOT a hostile-descendant containment or OS-level
egress-isolation claim. A scrubbed child environment and fresh temporary HOME
contain no inherited tokens, proxies, netrc or production values. ImportFence
denies application database/settings/pipeline and model modules. Offline mode
also denies socket/DNS/Requests network paths. No database imports or persistence.

## Structural output and privacy

Artifact schema: oldham-form-metadata-v1, compact sorted JSON <=16,384 bytes.
Top level contains identity/time/mode, fixed source host/path, HTTP status,
execution status/fixed failure category, counts/bytes/time/accounting and form.
Interrupted accounting is UNKNOWN/null, never fabricated zero.

Form selection requires exactly one form containing the exact reference-input
name. Report form count and selected ordinal, GET/POST/UNKNOWN method, and only
recognised Oldham search action paths; unsafe/unexpected actions are null. They
are never followed. Form IDs, action queries and arbitrary method strings are
not exported. Max20 forms,80 controls and500 options per select; overflow fails.

Controls report ordinal, bounded identifier or redaction, type, named/populated,
disabled/checked/multiple, option count/selected ordinals, duplicate-name flag,
whether current verifier harvests that input, classification candidate and
bounded rejection category. Values are inspected transiently only to produce
booleans/classifications. No value, option value/label, HTML, cookie/header,
state/token, arbitrary error text or populated planning text enters the artifact.

Only independently fixed identifiers in SAFE_NAMES can be emitted (all <=64
characters). All unknown names, including token-like/oversized identifiers, are
redacted to ordinal. This deliberately prioritises privacy: a redacted unknown
may still require later review to establish its purpose. Presence/type/population,
duplicate flag and verifier-collection category remain observable. No automatic
compatibility correction can be justified solely by this observation.

Candidate labels retain the requested six-category taxonomy. REQUIRED_SERVER_STATE
means a recognised state-field candidate, not proof it is required or safe.
APPROVED_* labels are diagnostic candidates only: classification_is_approval:false.
Unknown populated fields remain UNKNOWN; populated search criteria are prohibited
expansion candidates. No changes to actions_canary/Idox/contract allowlists.
Disabled/submit/checkbox classification is not browser successful-control truth:
the output separately records structural properties and the existing verifier's
input-harvesting behaviour. Disabled fieldset handling is conservative and does
not model the first-legend exception. Current form metadata cannot prove the
exact historical form/field/value involved in the consumed failed run.

The supervisor validates a CLOSED schema and enum/static-identifier allowlist
before transfer. Invalid/missing/oversized artifact yields bounded FAIL metadata
only. Temporary artifacts are removed on supervisor completion; only the bounded
validated artifact is uploaded with seven-day retention.

## Acceptance and hosted evidence

`tests/test_oldham_form_metadata.py` covers hidden state, reference, search fields,
select/radio/checkbox/submit/disabled/duplicate/empty/populated controls, unsafe
identifiers, multiple/malformed forms, wrong method/action, actual body limits,
redirect/second-request/POST/URL denial, schema privacy and independent hung-worker
termination. No existing assertion is weakened.

Companion `l1-registration-offline.yml` runs the new and existing gates under
network-denied pytest and executes this exact runner in OFFLINE mode with one
synthetic response. It asserts COMPLETE, zero council requests and bounded JSON.
Its automatic CI triggers can only run mocks; the dedicated live diagnostic is
workflow_dispatch-only and is not yet registered on master.

Future live authority, after separate reviewed registration: ONE diagnostic GET,
the fixed origin/query, zero redirect/retry/POST, <=2MB response, <=30s worker,
<=3min outer job, <=16KB metadata. No retry under that one-use authority.
No Failsworth/Southlink submission, facts, councils beyond Oldham, DB, repair,
bootstrap, monitoring, models, summaries, Render or Arcus work is authorised here.
