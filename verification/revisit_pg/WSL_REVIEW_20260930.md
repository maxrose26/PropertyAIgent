# First native revisit archive inspection and local repair

Archive SHA256 e1924805a83364f7a219c0a4b6509138bbbbd7f9a102ccd0ae4bbea78c52aac2
matches the supplied checksum; all included file manifests verified. Candidate
cb0df78a6c6fc9a4e27114ade117cd8ca3b9d05f and empty before/after tree records verified.

Actual WSL run: PostgreSQL16.15 Ubuntu, Python3.12.3, pytest9.1.1,
psycopg3.3.6, libpq180006. Pinned dependency preflight has no errors.
Private namespace/cluster identity was recorded. stop.log confirms server stopped.
Native JUnit:17 tests,3 passed,2 failed,12 setup errors,0 skips;24.956seconds.
The passing tests cover pre-P0-A refusal, unrelated/partial schema refusal and
ordinary-engine refusal. They do not establish successful revisit migration.
All14 failures/errors report revisit stage check drift; dependent behaviour did
not execute past setup. No native acceptance.

Diagnosis: migration.py assumed one non-pretty representation while SQLAlchemy
PostgreSQL reflection explicitly invokes pg_get_constraintdef(oid,True) and
strips outer parentheses. The first archive did not log the observed expression,
so its exact spelling is not asserted here. The failed comparison is established;
formatting mismatch is supported by inspection of the pinned dialect code.

Repair: query pg_get_expr(conbin,conrelid,false) directly and compare the strict
non-pretty expression. Remove only enclosing expression parentheses; do not
normalise casts/literals/operators. Require the exact constraint name, validated
state and normal inheritance; report observed expression on failure. No allowed
stage, schema DDL, P0-A allowance, ownership or admission rule changed.

Seven focused offline regressions exercise strict comparison and rejection of
altered expressions, wrong name, NOT VALID, NO INHERIT and missing/extra checks.
Three new native cases alter the actual canonical table constraint and require
refusal. Runner now requires20 native cases with no skips. The repair has49
passing offline tests,0 failures/errors/skips;20 native cases collected only.
No native rerun possible here: server binaries remain absent; no installation
attempted. A revised exact-commit handoff is needed, and its returned archive
must be inspected before claiming the repair passed PostgreSQL.
