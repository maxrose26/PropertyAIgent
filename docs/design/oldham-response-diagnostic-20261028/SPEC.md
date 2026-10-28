# Oldham single-page response diagnostic (offline; inactive until the owner approves its exact hash)

Baseline `97db278d90027fd9777b5071191a94ce7f62a182`. Stage 4 remains OPEN. This is a diagnostic, **not** a collection observation: it admits no record, changes no completeness and has no
publication path.

## Question
Oldham RECEIVED 15-21 October 2026 returned five unique records with no `p.pager` count or terminal marker (observation `oldham-metadata-once-20261028`, evidence commit `d0eea18a`, outcome UNKNOWN,
authority consumed). The parser and the structural proof read counts and next links only from `p.pager`, and the retained projections cannot show whether a count or navigation signal existed elsewhere
in the HTML. Five rows below page size 10 proves nothing. The smallest evidence that can answer this is the search response itself, kept privately, once.

## Capture (reuse, no new transport)
* Exactly two requests through the existing `WindowBoundary`: the search-form GET and the exact date-search POST (Oldham, RECEIVED, 2026-10-15 to 2026-10-21). No sort, refine, paging, detail, retry, replacement, or redirect following (a redirect is a failure).
* Existing ceilings, not derived from the earlier response sizes: 500,000 bytes per response (combined 1,000,000 = 2 x 500,000), 45 s reader budget, 3 s connect / 8 s read dispatch, 50 s supervisor deadline, zero retries.
* Raw bodies are written to `~/.local/state/propertyaigent-diagnostics/<identity>/` (directory 0700, files 0600, created exclusively). The identity directory is the single-use claim; an existing one refuses.
* The export (`audit.json`, also printed) holds only: per-response phase, HTTP status, allow-listed media type, redirect disposition, byte count, SHA-256 and private file name, plus request accounting. No
  headers, cookies, URLs, HTML or record text. Nothing is published or committed.

## Authority (inactive until approved)
`render` produces a local registration (identity, scope, revision/tree, limits, issue and expiry within two hours, `database_synchronised: false`, `publication: NONE`) and prints its hash. `run` refuses unless
the exact hash matches, the registration is current, the checkout is clean at the registered revision/tree, `--enable-reviewed-source-only-diagnostic` is given, and no DATABASE/SUPABASE/OPENAI/ANTHROPIC
variable is present. It does not read or synchronise database stops, and it has no remote control or head check: cancellation is local Ctrl+C / SIGTERM only. Existing Salford/global and manual stops are unchanged.
Containment is a transient user scope (`MemoryMax=1 GiB`, swap 0) plus the 50 s supervisor; it does not use the release controller's cgroup enforcement, so closure is process-exit evidence, not cgroup readback.

## Inspector (pure, offline, no request)
`inspect_html` reports structure only, never the results list or its text: count-like text outside the results list (with element chain), navigation-like elements and links (classes, rel, disabled state, parameter names),
count/page inputs, numeric assignments in scripts, meta tags, `resultsPerPage`, and what the existing parser extracts from the same bytes (rows, first/last/total/terminal, next link, `p.pager` count).
It reports observed facts. An absent signal in one response proves nothing about the portal in general.

## Not in scope
Any parser or proof change (that follows only from evidence), partial admission, other councils, publication, database access.
