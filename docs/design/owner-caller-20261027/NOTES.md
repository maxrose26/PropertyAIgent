# Owner caller connection (offline slice): limits, evidence, and what is not authorised

Scope: connect the owner/runner tooling to the integrated chain of PR #189 for one Idox council (Tameside) and one Arcus council (Manchester), offline, against a disposable database. Nothing here registers,
issues, or runs live authority. Bolton's single-use ceremonies keep their own constants and are not chain scopes.

## Which limit applies at each layer (`verification/ingestion_storage/limit_reconciliation.py`)
| Layer | Idox (Tameside) | Arcus (Manchester, BROWSER_SOURCE_V2) |
|---|---|---|
| reader | historical envelope: worker 45 s, source outer 49 s | worker 75 s, source outer 80 s, source memory 1.5 GiB, rss ceiling 1.5 GiB |
| supervisor | `operational_supervisor.supervise`: source child 45 s, other 165 s | release `Source.run`: kills the source cgroup at 80 s; slot active 90 s |
| ledger item `limits`, enforced after the work (`validate_source_resources`, `validate_outer`) | `DEFAULT_LIMITS` (worker 45, outer 60, source_rss 1 GiB, aggregate 1.5 GiB) | `BROWSER_SOURCE_V2_ITEM_LIMITS` (worker 75, outer 90, source_rss 1.5 GiB, aggregate 1.5 GiB) |
| grant | `expires_at` > now and <= 24 h (SQL), source_calls = nominees, writes = 2 x nominees, lifetime >= slot + 165 s x (batches + nominees) | same |

Finding (confirmed by test): the V2 budget does not fit `DEFAULT_LIMITS` (worker, outer and source_rss); a V2 audit would be rejected by the ledger AFTER the browser work. The selection is now refused at
registration and by the caller's preflight, naming every violated field. Nothing is raised, clamped or substituted: compatible limits are an explicit reviewed constant that reconciliation verifies.

## Outer-supervisor evidence
* Idox: `operational_supervisor.supervise` already returns a compliant outer object (exit code, survivors, peak, `accounting_complete`, cleanup). Unchanged.
* Arcus release slots: `Source.run` now adds `outer_supervisor` to `owned_cleanup` for execution-budget (V2) registrations only, built by `outer_evidence.outer_supervisor` from the child's observed exit code, the
  elapsed time and the source cgroup's own `memory.peak` / `cgroup.procs` readback. An unreadable value is `None` and `cleanup` is `UNKNOWN`; nothing is inferred from the exit status. Historical release versions' receipts are unchanged.
* Not shown offline: real kernel cgroup behaviour. The tests run the real `Source.run` and `supervise` over real child processes with a temporary directory standing in for the cgroup files.

## Not authorised / remaining (exact)
* Issuing live authority for another council needs a reviewed policy step: `ingestion_register_bolton_exception` accepts only the pinned Bolton scope and named authorities (`BOLTON_ONLY`, `EXACT_BOLTON_DAY`, fixed stop-checkpoint hashes). `Owner.register` therefore cannot be run for Tameside or Manchester; the tests install the prepared registration into a disposable control record instead.
* Rochdale: no initial-status literal is recorded in the repository. Three separately pinned places name the accepted literals (`app/pipeline/status_verification.py` allowed map, `verification/direct_reference/arcus_adapter.py` expected map, the state set in `committee_exact` / `new_identity_contract`). Rochdale needs a reviewed observation of its initial-status literal and source host first; it is refused with `SCOPE_ROCHDALE_INITIAL_STATUS_UNQUALIFIED`.
