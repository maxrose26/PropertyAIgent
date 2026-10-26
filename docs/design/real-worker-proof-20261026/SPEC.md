# Real worker path: dependency binding, failure evidence and regression proof

Status: approved offline workstream. Local branch only; nothing is pushed, merged, installed into the controller
environment, published or released. No council or database contact. Stage 4 remains OPEN; live execution NO-GO.
Baseline: master `537b01d57c4079dadd0982f472fddb113cc14498`. The consumed release
`three-council-v2-source-once-20261026` and all its receipts are preserved and are not replayed.

## Historical conclusions (unchanged)
* The missing `rapidfuzz` is **reproduced offline** but **not directly proven** as the live cause: the live worker's exit
  status, stdout line and traceback were never retained.
* The historical live descendant (`live_child_count: 1`) remains **unidentified**: it was not reproduced offline and no
  identity was retained.

## 1. Dependency binding and preflight
**Exact version, from existing project evidence:** `verification/ah_pg/requirements.lock` pins `RapidFuzz==3.14.6` (the lock the
hosted CI environment installs; `requirements.txt` lists `rapidfuzz` unpinned). The controller virtualenv already matches the lock
exactly for `requests 2.34.2`, `beautifulsoup4 4.15.0`, `lxml 6.1.3`, `playwright 1.63.0`, `psutil 7.2.2`, `cryptography 50.0.1` and
`SQLAlchemy 2.1.1` (the last is imported by the same `site_linking` chain). Only `rapidfuzz` is absent.

**V2-only binding.** `PACKAGES`, `DEPENDENCIES` and `SUCCESSOR_DEPENDENCIES` are unchanged, so the V1 registrations and manifests keep
their exact bindings. `THREE_COUNCIL_SOURCE_RELEASE_V2` additionally binds the distributions `rapidfuzz` and `SQLAlchemy` (the installed
version of each is recorded in the registration) and the files `verification/ah_pg/requirements.lock` and
`verification/discovery/runtime_dependencies.py`.

**Runtime check** (`verification/discovery/runtime_dependencies.py`, council-free, no database side effects). Run by the launcher and by
`four_council_release run` before any claim, in the interpreter that will execute the release:
1. every bound distribution is installed at exactly the version pinned in `requirements.lock` (names absent from the lock need only be present);
2. a static scan (`ast`, nothing executed) models what actually loads: the eager imports of the bound modules, plus the lazy
   (function-level) imports of the BOUND modules themselves (one hop, e.g. `site_linking`), each expanded by its own eager imports;
   imports guarded by `try/except ImportError` and `TYPE_CHECKING` are optional; lazy imports of other modules are not followed
   (reachability is not statically knowable; the runtime proof in section 4 covers them). Every third-party top-level name found must
   be resolvable (`find_spec`; a blocked or broken finder counts as missing);
3. that first-party set (except `app.db.session`) is imported in a child interpreter with a minimal scrubbed environment,
   a 60 s timeout and bounded output. Importing `app.db.models` only declares ORM classes; no engine is created.
Failures are reported as module/distribution names and exception class names only, then `Stop('RUNTIME_DEPENDENCY_CHECK')`.
Rendering a V2 registration records the installed version of every bound distribution and refuses (`PackageNotFoundError`) on an
interpreter that lacks one, so a registration cannot be produced against an incomplete environment; the V2 launcher and
`four_council_release run` run the check, in the launch interpreter, before any claim. Historical versions are not gated.

## 2. Owner environment (prepared, not applied)
`docs/design/real-worker-proof-20261026/OWNER-ENVIRONMENT.md` holds the exact minimal command and verification. The controller
virtualenv is not modified by this workstream.

## 3. Failure evidence (additive; no gate relaxed)
* **`source_closure.worker_exit`** is recorded only when the worker exits non-zero on its own: `returncode` (or `signal`),
  `reason` and `reason_state`. The worker's stdout is read through a bounded (4 KiB) non-blocking pipe; the surplus is drained and
  discarded. The single line must be a JSON object with exactly `status`, `reason`, `cleanup`, with fixed `status`/`cleanup` values and a
  `reason` that is a member of the fixed allowlist `WORKER_EXIT_REASONS`. Anything else is `MALFORMED`, an unlisted code is
  `UNRECOGNISED`, no output is `ABSENT`; the raw text is never stored, exported or executed. The primary failure
  (`SOURCE_CHILD_FAILURE`) is unchanged in every case.
* **Worker guard:** `ImportError` now prints the fixed reason `DEPENDENCY_UNAVAILABLE` instead of the generic `PREPARATION_FAILURE`.
* **Descendant identity** at both closure readbacks, only when children are seen: at most 8 entries of `pid`, `ppid`, `name` (a
  restricted character set, 32 characters), `status`, `age_seconds` and a coarse `group` (`SOURCE`/`CONTROLLER`/`OTHER`/`UNAVAILABLE`);
  never a command line, environment or path. Unreadable fields are explicit `UNAVAILABLE`; clean receipts are byte-stable.

## 4. Regression proof of the real worker chain
`tests/real_worker_proof_runner.py` runs the **unmodified** `Source.run` for slots 1-3 under a real V2 user scope: the production
command, environment, working directory, session, cgroup attach, worker, `finite.read`, `supervised`/`supervise`, probe child, real
Playwright/Chromium and real `requests`. It then applies the unmodified `Launcher.accept`. `tests/test_real_worker_proof.py` orchestrates
it (opt-in with `REAL_WORKER_PROOF=1`; skipped otherwise, including under the offline CI wrapper):
* **Network:** a user+network+mount namespace with only loopback. The kernel enforces it; the runner asserts that external connections fail.
* **Content:** a local fixture server (loopback, TLS) for `account.rochdale.gov.uk`, `publicaccess.tameside.gov.uk` and
  `planningpa.oldham.gov.uk`. Rochdale is a synthetic Arcus-shaped listing (12 rows, 2 pages, the Aura POST the probe accounts for);
  Tameside/Oldham serve the existing reconstructed Idox bodies (`tests.test_discovery_four_council_proof.bodies`) in request order.
* **Name and trust plumbing without touching the processing path:** a hosts-file overlay and a CA-bundle overlay (bind mounts visible only
  inside the namespace). Chromium uses its built-in NSS roots and cannot be given the fixture CA by overlay, so the proof interpreter
  (an overlay venv created in the test) carries a `.pth` hook that, only when the namespace's hosts overlay is present, adds
  `--ignore-certificate-errors` to the Playwright launch. This is the single deviation; commands, environments and process layers are production's.
* **Controls:** (a) the same chain with `rapidfuzz` import-blocked (worker exit 1, `DEPENDENCY_UNAVAILABLE`, `SOURCE_CHILD_FAILURE`, recorded
  return code); (b) a deliberate crash (pre-existing exclusive output file; exit 1, `PREPARATION_FAILURE`).
* **Passing criteria:** exit 0, a valid audit, every record carries `processing_screen`, `Launcher.accept` returns `COMPLETE`, closure
  complete, zero survivors, scope `success`.
* **Interpreter under test:** the overlay venv borrows the package set of `REAL_WORKER_PROOF_BASE_PYTHON` (default: the pytest
  interpreter). The fixture server and namespace setup always run under the pytest interpreter. Pointed at the controller venv before the
  owner install, the chain tests fail with `DEPENDENCY_UNAVAILABLE` (retained evidence); after it they must pass.
* **Remaining proof gap (stated, not hidden):** hosted CI wiring (needs a push); the live interpreter itself (needs the owner install, then the
  same test with `REAL_WORKER_PROOF_BASE_PYTHON`); real portal content, size and latency; the Chromium TLS deviation above.

## Not included
Parser expansion, a generic framework, resource or time changes, a retry policy, prepared-cache work, controller-environment changes,
publication of evidence, a new release.
