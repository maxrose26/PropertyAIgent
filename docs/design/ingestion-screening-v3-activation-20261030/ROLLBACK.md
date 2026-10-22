# Screening v3 activation: recovery and rollback sequence (PR #175; nothing here is executed by the candidate)

Immediately before each script the owner re-runs the inventory verification on the SAME connection (the scripts themselves check nothing and are unconditional CREATE OR REPLACE). Rollback is an OWNER terminal action. It is never automatic, never a retry, and never run blindly: the owner first reads the inventory state and the authority state, and chooses the row below that matches what was observed. Every function-restoring script is transactional (BEGIN/COMMIT), so a script either took effect completely or not at all; a state matching no reviewed inventory is therefore evidence of something other than an interrupted script and is never rolled back.

## What is restored, separately
| Object | Installed by this candidate | Restored to (reviewed, byte-exact) | Script |
|---|---|---|---|
| `ingestion_worker_step` | derived v3 worker function (six substitutions) | the ORIGINAL worker function, as in every accepted inventory | `worker-step-original.sql` |
| `ingestion_bolton_allowed`, `ingestion_register_bolton_exception` | policy v6 (one more named allowance) | policy v5 (the generation-3 window policy: the two consumed window names) | `docs/design/ingestion-window-demonstration-20261023/policy-window-allowance.sql` |
No other function, role, membership, secret, stop value or control field is touched by installation, so none is restored. Restoration is verified against the reviewed inventories `GENERATION3_WINDOW_POLICY_APPLIED` (v5 + original worker), `GENERATION3_SCREENING_V3_POLICY_APPLIED` (v6 + original worker) and `GENERATION3_SCREENING_V3_APPLIED` (v6 + v3 worker). The order of restoration is always worker function first (v3 admission stops), policy second.

## A. Before any authority is issued (installation ceremony, no registration)
| Observed inventory | Meaning | Recovery |
|---|---|---|
| `GENERATION3_WINDOW_POLICY_APPLIED` | the ceremony stopped before changing anything (its first step verifies this exact state and fails closed) | none; nothing to restore |
| `GENERATION3_SCREENING_V3_POLICY_APPLIED` | policy v6 installed, worker function still original | apply the v5 policy script only; verify `GENERATION3_WINDOW_POLICY_APPLIED` |
| `GENERATION3_SCREENING_V3_APPLIED` | both installed, no authority | apply `worker-step-original.sql`, verify `GENERATION3_SCREENING_V3_POLICY_APPLIED`; then apply the v5 policy script, verify `GENERATION3_WINDOW_POLICY_APPLIED` |
| mixed / unrecognised / owner or search-path changed | not a reviewed state | STOP. Do not run any script. Preserve the journal and the per-function hashes; reconciliation by explicit decision |
In every case first confirm by control observation that the control record is byte-identical to the baseline (digest unchanged) and that the screening allowance name is absent from grants and exceptions. If it is present, use section B.

## B. After authority issuance
0. If the owner process died after registration there is no reviewed tool to invalidate (invalidation acts on the running owner's own authorities): do nothing, let the 900 s grant lifetime lapse, and go to section C.
1. Confirm invalidation FIRST: the grant and the exception for the one named allowance are expired/revoked in a COMMITTED readback (`ACKNOWLEDGED_READBACK` or `ALREADY_INVALIDATED_READBACK`). Invalidation never depends on stops or generation and sets only the two expiry values.
2. Reconcile active work: read the 59 bound items. No item may be claimed or in flight; the hosted job must have published its result or its stop, or the grant lifetime (900 s from registration, never extended) must have passed. Items COMPLETE or untouched are left exactly as found: the 30 retained rows and any completed new items are evidence and are not deleted or rewritten.
3. Only when 1 and 2 hold: restore the worker function, verify, restore the policy, verify (section A rows).
A successful run needs no rollback; leaving v6 and the v3 worker installed with the allowance invalidated and expired is a valid end state, and restoring them is the owner's choice.

## C. Uncertain invalidation or execution state
Any of: `UNCERTAIN_RECONCILE` invalidation, an uncertain commit, no committed readback, an item set that cannot be read, a hosted job still running, an unconfirmed cleanup, or `STOP_RECONCILE_NO_RETRY` with an unexplained phase. Then NO rollback script is run and nothing is replaced or re-run. Preserve the journal, the published evidence and the hosted artefact; take one read-only observation of the control record and the 59 items; the stop stays in place; reconciliation is an explicit owner decision recorded before any later action. A second registration of the same name is impossible by design.
