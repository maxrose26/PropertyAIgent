# 038 — Fixed Oldham read-only inspection of the installed state

Status: implemented dormant; **not authorised for execution**. Layer: operational readiness for the Planning Applications / Build Status layers (it makes no Site more intelligent by itself; it establishes whether the next authentic Oldham capture and screening can safely run).

## 1. Purpose
Before the retained five Oldham records are authentically captured and screened, establish — read-only — whether the existing production environment supports it: destination route, installed worker and Oldham policy function identities, runtime privileges, stop/control state, and role and session state. Not admission, display or another scrape.

## 2. Mechanism (reuse, not a new access framework)
A sibling of the single-statement administrative probe (`admin_connection_probe`): the same hidden input, route/TLS preparation, journal, memory supervision and closure accounting. It reuses the reviewed fixed SQL of `Owner.pipeline_readback` and adds only plain SELECTs. `Owner` is imported solely for its pure inventories and is never instantiated. The historical probe, `Owner.pipeline_readback` and the runner are unchanged.

## 3. Rules
1. One connection; `BEGIN READ ONLY`; at most nine SELECTs; `ROLLBACK`. At most 11 planned and 12 permitted driver statements (the existing ceiling, not raised). Statements are a closed constant list sent through one gate; nothing else can be sent.
2. No GRANT, SET ROLE, installation, role change, credential handling beyond the hidden connection URL, GitHub, direct ledger table SELECT or council contact. (The control row is read only through the installed SECURITY DEFINER control function.)
3. Function state is one of: `RECOGNISED_PRE_OLDHAM` (naming which reviewed state; the retained v3 state is flagged), `OLDHAM_EXACT_INSTALLATION`, `NOT_INSTALLED`, `MISSING_OBJECTS` (naming the missing functions), `UNEXPECTED_OR_MIXED`. Bodies are compared by SHA-256 computed in the server; owner, `search_path`, signature and overloads are checked. A discrepancy is reported, never repaired. The verdict covers body hash, owner, `search_path`, overloads and the Oldham helper's signature and SECURITY DEFINER flag; it does not check volatility, strictness or other functions' definer flags, and says so. Several reviewed states share most bodies, so a partial installation consistent with more than one state names all candidates and chooses none.
4. Visibility the identity lacks (`pg_read_all_stats`, `pg_authid` password presence, control function EXECUTE) yields `UNKNOWN`, never a guess.
5. The control function exposes only: global stop, manual stop, stop generation, count of unexpired grants. It does **not** expose `last_hard_stop`, the stop-state digest, WRITE_INTENT uncertainty rows, Oldham allowances or per-grant detail. The report says so and does not claim barriers absent.
6. Output is a fixed-field report: booleans, allow-listed values, counts and fixed codes. No password or verifier value, credential, query text, application record or arbitrary exception text.
7. The proposed identity is the existing administrative `postgres` migration account (hidden input). READ ONLY is a per-transaction guard; the account is not restricted. TLS is verified only by the existing route mechanism at any later approved connection and is not claimed here.

## 4. Non-goals
No restricted read credential, role, grant, installation, registration, stop change, or readiness verdict. The result informs a later owner decision.
