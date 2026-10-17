# Owner successor attempt — STOP, no replay

Stage4 OPEN. Owner-local integrated controller dc8d266224097c35cc1475964b0fd7a54f31490e,
tree258c35bf37859e9f5bfd4c453e2e953ba15e0ccf. Registration
cfc38625cca22de33d973f42851d3ea908d0b35f2a9e2ccc7e7000e52b42b082 is now CONSUMED.
Systemd invocationc974ab5bf21247969d66ae2eaaac748c; local execution, no GitHub Actions run.

Owner supplied terminal/audit text, independently verified all16 chain entries,
7005bytes, SHA2565dda1e97c8dfc2a9a899c839e9c60d88f3c08bff05d5172579ad2efe1ade279e,
chainhead0fba5e2d028a1c054a556bc05d6c744caa673a49d4ba0c3dc290d3aeb9d8138e.
Original owner machine/file not remotely accessed. Archive reproduces the supplied
journal bytes matching the supervisor digest; original directory remains intact.

Outcome STOP_RECONCILE_NO_RETRY / MIGRATION_IDENTITY / cleanup UNCERTAIN.
Owner access VERIFIED; approved session-pooler route/verify-full selected18.135.253.94.
One DB connection, four top-level driver statements: three session SET timeouts
and read-only current_user/session_user/rolsuper/rolcreaterole/rolbypassrls SELECT.
Connection_closed acknowledged; open_connections0. Active DB0.26088705100028164s,
39returned serialized data-value bytes (not network traffic). No install.sql,
role/object mutation, password generation, protected-secret mapping, activation,
seed, storage test or teardown reached. No uncertain migration/seed/password commit
because no such statement was executed. Overall historical cleanup remains
UNCERTAIN; do not relabel it CLOSED from partial closure facts.

Memory correction succeeded in actual WSL:1.1728088340005343s supervised,
peak owned sampled RSS91066368bytes; outer kernel charge peak119021568bytes,
child15392768bytes; no child/outer max/OOM events. Child populated0,group removed,
no forced cleanup,zero reported owned survivors. These do not prove whole cleanup.
Cumulative supervised spend with previous .11050213100043038s is
1.2833109650009647s; DB connection attempts1of13. No allowances reset.

Specific controller inconsistency: storage_controller.py expects
('postgres','postgres',False,True,False), requiring migration NOBYPASSRLS.
Accepted retained DECISION.md at this integrated revision explicitly records the
existing migration postgres role as NOSUPERUSER/CREATEROLE/CREATEDB/BYPASSRLS from
consumed accepted run38907801607. install.sql requires non-superuser CREATEROLE,
not migration NOBYPASSRLS. Runtime logins MUST still be NOBYPASSRLS and remain
unprovisioned. No permission expansion, new credential, stronger fallback or role
alteration is needed to resolve the code/baseline inconsistency.

The actual returned identity tuple was not retained. Its39serialized bytes are
consistent with the recorded baseline but byte length is not identity evidence.
Do not assert a freshly verified tuple or infer which single flag differed.
No new live query/replay is requested by this report. Smallest review decision:
correct the migration-only gate against already accepted authoritative flags,
retain strict runtime restrictions, add focused negative tests and retain safe
non-secret flag readback on any future authorised observation. Any successor must
explicitly account for BOTH consumed attempts, exact bindings, original expiry,
remaining time/connections/output and all historical uncertainty stops.

Original memory-failure attempt and both audit directories/consumed registrations
stay preserved. Production provisioning/storage acceptance NOT COMPLETED. No
source/application/factual effects,stop release,consumer,scheduling or advancement.
