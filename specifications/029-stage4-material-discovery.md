# Stage 4 material new-application discovery

Status: implementation in progress; no production admission or coverage claim.
Authority: Product Owner instruction of 14 October 2026, following approved design.

## Product contract

Discover official identities absent from the frozen database identity set. Keep
discovery, deterministic qualification and ranking separate. Unknown scale,
relationship, or sparse/conflicting metadata is retained for qualification.
The existing 10-unit threshold is not a hard discovery filter. No opportunity,
site, buyer state, ownership or availability assertion is created by discovery.

Required councils: Bolton, Bury, Manchester, Oldham, Rochdale, Salford,
Stockport, Tameside, Wigan. Trafford is excluded from execution.
First engineering cases: retained Bolton evidence and Manchester (predeclared
before any new acceptance observations). Portal or official publication list
may be primary, whichever is demonstrably simpler and complete.

## Completeness and identity

Every window has exactly one COMPLETE / INCOMPLETE / FAILED / UNKNOWN outcome.
COMPLETE requires a qualified source contract, evidence of applied interval,
terminal-page/list evidence, complete accounting, no caps or failures and
explicit zero evidence where empty. Partial results are retained but never
advance the completed-through boundary. Contiguous completed intervals only;
a newer completed window must not conceal an earlier gap.

Use source-displayed council/reference identity, not request parameters.
Duplicate conflicting observations are withheld rather than first/last-wins.
Preserve existing field-state vocabulary including UNKNOWN. Retain all
enumerated identity outcomes and deterministic exclusion reasons.

## Persistence

Existing Application uniqueness (council_code, reference) is reusable.
Legacy upsert is not the admission path: it writes facts directly, loses blank
semantics and assumes later document/site stages. New identity admission must
be independently reviewed, idempotent, per-record, bounded and read back.
Pending discoveries must be isolated from automatic site linking, documents,
models and opportunity construction. No facts bypass B2. No material schema
or B2 redesign is authorised. Uncertain persistence stops without retry.

## Acceptance

Freeze exact candidate SHA/config/rules/date semantics/database identity set
before acceptance. Calendar rule: first full Monday–Sunday week beginning
strictly after the final candidate freeze, plus its consecutive week, Europe/
London. Audit after the following publication week. These future observations
cannot be substituted with historical fixtures or described as already run.
28-day initial overlap. Seven-day objective from demonstrable public
availability; received/validated dates do not supply publication timestamps.
Absent timestamp or independent observation: latency UNKNOWN.

Independent denominator from official lists or independently enumerated
windows, plus bounded manual committee-reference cross-check. All material
and possible-material references accounted; no unexplained material misses.
Unknown/zero denominator does not produce a numerical 100% recall.
Samples exercise shapes, not council coverage. Detection and admission are
reported separately. No manual insertion may conceal a missed reference.

## Boundaries

Reuse bounded workers, accounting, provenance, cleanup and B2. No recurring
scheduling, Trafford requests, model calls, document/committee ingestion,
paid supplier, deployment or Stage 5 work. Guarded integration uses
[skip render]. Operational discovery and Master Stage 4 remain unaccepted
until independent review and the specified live/prospective evidence exist.
