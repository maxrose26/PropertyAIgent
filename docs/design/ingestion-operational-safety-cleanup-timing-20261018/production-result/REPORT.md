# Production cleanup: successful access readbacks; final audit collection pending

Owner executed the exact timing successor at integrated revision acd3f5690b439d7d91b7a7efb9ace79c9098d303, helper SHA25666467e6396fffe6ae4e8a8860f1b22b50a102dbad3814e5d8e4058ca2d72be7b and registration SHA2563a1f7e58506d507deb9bf5c1b60c08af8c7a4ea2202785d27344e53d404f696f. Owner script checksum, clean integrated checkout/tree and registration/helper checks passed. Unit invocation20b631ad9acf43889f0cbfa5f1be44f4.

Controller status SAFETY_CLEANUP_ACCESS_DISABLED; database_commit ACKNOWLEDGED; cleanup CLOSED; controller_exit_status0.

Actual reconnected readbacks: ingestion_effect_login and ingestion_worker_login are NOLOGIN, password-null true, NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOBYPASSRLS/NOREPLICATION. Reviewed memberships are absent; associated sessions[]; two native connections opened and closed. Both exact temporary secrets are acknowledged deleted by the successful helper: INGESTION_WORKER_DATABASE_URL and INGESTION_EFFECT_DATABASE_URL. The exact helper only reports success after final names-only absence verification and DATABASE_URL/all-other-secret preservation.

Actual usage:20driver commands,2connection attempts,17,236returned database data-value bytes,0.470817414989142driver-active seconds,2DELETEs,2names-only GETs. Hidden input7.522071788000176seconds. Active through audit flush2.1679117449966725seconds; total through flush10.27219113799947seconds. Kernel peak64,049,152bytes, zero max/OOM/kill events. Live children0/new sockets0; controller only in scope at final snapshot. Persisted evidence41,362bytes; terminal JSON2,174bytes; helper-reported combined43,536bytes. No council calls, application writes or pipeline retry.

Verification: reconstructing the saved canonical final-result.json from the owner receipt reproduces SHA256da098789bde167157b09d85ae8379e095f77b45bf2cd930c7a52a54cf34f3c0d exactly (1,475bytes). Terminal JSON size and persisted+terminal arithmetic independently match. The full expected39,887-byte events.jsonl is not yet received: reported SHA256a28b06aadc13ee0eb7bd2362c40ec7111804777febf230e44041fae2de116ec7, chain headca6922b1c24394b1f3da77ccbbcc0ff97dda9ae3051aa1ba98ef939ddbe895ee. Full chain/control/ledger/secret event verification and archival remain pending.

Separate local post-exit systemctl inspection timed out: scope_readback_exit_status124. It did not execute DB or secret effects, does not undo committed cleanup, and is not permission to rerun the controller. The controller explicitly did not claim scope removal before exiting. Post-exit kernel-cgroup absence/emptiness remains independently unestablished.

Next action is credential-free collection of the existing audit and a bounded direct-kernel check of this exact owned scope; no further DB connection, GitHub secret request, mutation, new registration or controller execution is needed or authorised. Production access effects have successful matching result readbacks; final independent cleanup acceptance awaits that evidence.

Both historical UNCERTAIN attempts and original operational accounting gaps remain unchanged. Storage remains accepted, operational acceptance failed, pipeline retry HELD, Stage4 OPEN.
