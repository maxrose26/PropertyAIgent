# Connected attempt: closed before collection

The owner started the approved control on 3 November 2026. Its terminal
receipt at 22:02:03.607746087Z reports CLOSED, pipeline NOT_VERIFIED,
failure at QUALIFY, no job ID, no source result and no independent finalisation.
Period: b-dbpilot-20261027-1102-01. Fixed historical window is unchanged:
27 October–2 November inclusive; Tameside RECEIVED, Manchester VALIDATED.

The existing successful build receipt was reconciled durably and independently
read back before the run. Artifact dep-dbl59a6i0phs738hhaj0 / application
7027e2e50a4b207406aa726a6eb74dbd43f1d480 is retained. The database evidence
migration had already committed. Neither needs repeating.

The executed qualify method unconditionally constructs DatabaseBudget with
statements=4 before creating its first engine. That class requires at least20
statements, including its existing eight-statement cleanup reserve, and raises
CONTROLLER_CEILING. The safe-result allowlist omitted that identifier, yielding
UNKNOWN_FAILURE in the historical receipt. The correction uses the class's
minimum20 and preserves one connection,12 seconds and8192 returned bytes per
role. No source/runtime budget, SQL, permissions or release guard changes.
The correction also preserves CONTROLLER_CEILING as an allowlisted diagnostic.

Focused tests use the real budget constructor and synthetic connections. They
reproduce the old pre-engine refusal, exercise exact qualification SQL/TLS/route
arguments and success/failure cleanup, and verify a CLOSED attempt cannot
reopen. These are not live authentication or collection results.

Actual closure reports COMMIT_ACKNOWLEDGED, runtime access DISABLED, sessions
ABSENT, temporary owner REMOVED, no issued source authorities, and preserved
generation5. Configuration/environment equality and suspension are true.
Independent provider read confirms suspended, auto-deploy off, /bin/true and
the original schedule. No handoff was reached, so no handoff restoration write
was necessary. GitHub publication was NOT_REQUESTED; installation stays suspended.

Remaining blocker: the consumed RELEASE intent and CLOSED journal forbid
another run. The owner-state SQL namespace and retained job command both pin
the same exact period. Renaming a local path, resetting the journal or silently
changing the period would bypass those bindings. This amendment does not do so.
An explicitly bound continuation/successor decision is needed before another
opening; its smallest implementation must account for both fixed SQL namespace
and retained job identity. No automatic retry, replacement job or source rebuild
is performed by this correction. Actual restricted authentication and connected
collection/retention/screening/backlog remain unverified.
