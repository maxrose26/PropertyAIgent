# Owner environment change: PREPARED FOR REVIEW, NOT APPLIED

`~/stage4-owner/storage-controller-venv` has not been modified by this workstream and must not be modified by anything but this reviewed
step. No release is authorised by this document. The consumed release `three-council-v2-source-once-20261026` is not replayed; any
future attempt needs a new release ID, registration and decision.

## What is missing, and the exact version
`rapidfuzz` is absent. The exact version comes from the project's own lock, `verification/ah_pg/requirements.lock`:
`RapidFuzz==3.14.6` (the lock the hosted CI environment installs; `requirements.txt` lists it unpinned). All other bound distributions
are already installed at their locked versions: `requests 2.34.2`, `beautifulsoup4 4.15.0`, `lxml 6.1.3`, `playwright 1.63.0`,
`psutil 7.2.2`, `cryptography 50.0.1`, `SQLAlchemy 2.1.1`.

Evidence for the minimal install, from the installed copy of the same wheel in the existing dev environment
(`~/p0a-work/venv/lib/python3.12/site-packages/rapidfuzz-3.14.6.dist-info`): tags `cp312-cp312-manylinux_2_27_x86_64` and
`manylinux_2_28_x86_64` (the controller venv is CPython 3.12.3, x86_64); `Requires-Python: >=3.11`; **no required dependencies**
(`numpy` only under the optional `all` extra); it adds only the `rapidfuzz` package and its `dist-info`.

## The exact command (owner, one step)
Same flags as the project's `verification/ah_pg/setup.sh` (`--isolated`, the PyPI simple index), plus `--no-deps` and
`--only-binary=:all:` so that nothing else is resolved or built:

```bash
"$HOME/stage4-owner/storage-controller-venv/bin/python" -m pip --isolated install \
  --index-url https://pypi.org/simple --no-deps --only-binary=:all: 'RapidFuzz==3.14.6'
```
The project lock carries no hashes, so hash pinning is not available; the version pin and the wheel-only rule are the available controls.
Do this only while no release is running and no `propertyaigent*` scope exists.

## Verification straight afterwards (council-free, no database, no network use beyond the install)
1. The interpreter that will run the release agrees with the lock and every bound import loads:
   ```bash
   cd "$HOME/stage4-owner/pr122-storage-acceptance" && PYTHONDONTWRITEBYTECODE=1 \
     "$HOME/stage4-owner/storage-controller-venv/bin/python" -m verification.discovery.four_council_release runtime-check \
     --version THREE_COUNCIL_SOURCE_RELEASE_V2
   ```
   Expected: exit 0 and `"ok": true`, `rapidfuzz` `installed == pinned == 3.14.6`. (Before the install it exits 1 and names `rapidfuzz`.)
2. The real-worker regression proof against that same interpreter's package set (needs the dev environment that has `pytest`):
   ```bash
   REAL_WORKER_PROOF=1 REAL_WORKER_PROOF_BASE_PYTHON="$HOME/stage4-owner/storage-controller-venv/bin/python" \
     "$HOME/p0a-work/venv/bin/python" -m pytest tests/test_real_worker_proof.py -q -p no:cacheprovider
   ```
   Expected: every test passes (the real chain returns screened, accepted audits for Rochdale, Tameside and Oldham; the controls fail visibly).
   Before the install the chain tests fail with `DEPENDENCY_UNAVAILABLE` (retained run evidence).

## Rollback
```bash
"$HOME/stage4-owner/storage-controller-venv/bin/python" -m pip --isolated uninstall -y RapidFuzz
```
returns the environment to its present state (the V2 launcher then refuses before any claim, by design).

## After the install
The registration binds the installed versions (`rapidfuzz`, `SQLAlchemy` and the existing six). Rendering a V2 registration on an
interpreter without any bound distribution refuses (`PackageNotFoundError`), and the pre-claim gate and launcher refuse an interpreter
that disagrees with the lock. Nothing is claimed by the install itself.
