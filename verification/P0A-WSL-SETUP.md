# P0-A: beginner WSL setup — 29 September 2026

Gate A remains OPEN. This guide authorises no production activity. The commands below run locally on your laptop, not in Astra's remote workspace. The WSL wrapper is syntax-checked and reviewed, but has not been executed on your laptop. Stop at every checkpoint. If a command fails, return its error; do not change pins, remove guards or retry repeatedly.

## Python decision

Use Ubuntu's **Python 3.12.3 in a virtual environment** for this integration attempt. Do not replace `/usr/bin/python3`, use `update-alternatives`, install packages with `sudo pip`, or build a second Python merely to match 3.12.14.

Inspection found no exact Python check in the frozen runner, no 3.12.14 requirement in the dependency snapshot, and no patch-specific runtime guard in the relevant code/tests. The former 3.12.14 wording described the original measured environment too strictly. Python patch-level compatibility is expected, not proof of identical process behaviour. The snapshot is package pins, not complete Requires-Python metadata. The original temporary venv is no longer present, so installed metadata could not be re-read. Package availability and Python constraints must be verified by pip on your laptop before proceeding.

Acceptance conditions: retain every package pin, install the Chromium revision selected by pinned Playwright, record the actual Python version, and rerun BOTH candidate and baseline on that same WSL environment. Report 3.12.3 as a deliberate environment deviation from earlier 3.12.14 evidence. No executable version check is removed or relaxed; the original runner is unchanged. A resolver failure is a stop condition, not permission to substitute packages. If it establishes a real higher-Python minimum, return that evidence for a specific isolated-interpreter decision.

## Files supplied

Download `p0a-wsl-handoff.zip` and `p0a-wsl-handoff.zip.sha256` into your Windows Downloads folder. The ZIP contains the frozen-history Git bundle, original runner/dependency snapshot, technical handoff, reviewed specification, latest review/results, this WSL guide, the WSL wrapper, and `SHA256SUMS.txt` for every enclosed payload file. Keep the supplied filenames. The wrapper supplements, and does not edit, the tested runner.

### Step 1 — copy the download into Ubuntu and verify it

In the **Ubuntu terminal**, run:

```bash
mkdir -p ~/p0a-handoff
explorer.exe "$(wslpath -w ~/p0a-handoff)"
```

File Explorer opens your Ubuntu folder. Copy the two downloaded files from Windows Downloads into that folder. This is an actual file transfer; remote attachments are not already on your laptop.

```bash
cd ~/p0a-handoff
sha256sum -c p0a-wsl-handoff.zip.sha256
```

**Checkpoint:** must say `p0a-wsl-handoff.zip: OK`. If Explorer does not open, use its address bar `\\wsl.localhost\Ubuntu-24.04\home\maxrose26\p0a-handoff` (adjust the Ubuntu username if different). Do not run later commands yet if verification fails.

### Step 2 — install local tools

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends git unzip python3.12-venv postgresql-16 postgresql-client-16 iproute2 util-linux tini
cd ~/p0a-handoff
unzip -n p0a-wsl-handoff.zip
sha256sum -c SHA256SUMS.txt
id -un
python3 --version
```

Your Ubuntu password is entered locally when sudo asks; typing is invisible. Do not paste it into chat. PostgreSQL installation may create/start Ubuntu's default local cluster; our tests never use it. The runner creates its own disposable cluster on a separate temporary port.

**Checkpoint:** all checksum lines say OK, user is not root, Python reports 3.12.3 (record any different version), and installation completed without errors. No production database or credential is needed.

### Step 3 — create the clean test checkout

```bash
mkdir -p ~/p0a-work
git clone ~/p0a-handoff/p0a-wsl-verification.bundle ~/p0a-work/PropertyAIgent
cd ~/p0a-work/PropertyAIgent
git checkout --detach e1b53eb4b942eb7b27fa14b49a60731eb2179293
git status --short
git rev-parse HEAD
sha256sum specifications/019-p0a-bounded-discovery-reliability.md
```

**Checkpoint:** status has no output; commit equals `e1b53eb4b942eb7b27fa14b49a60731eb2179293`; specification hash equals `c007e2b2912ae5d8817142c32fdf35e0000f72d4fa127d5c83e32e6ef10970f8`. If the destination already exists, stop rather than overwriting it. Do not copy an existing application checkout or `.env`. Keep work under Ubuntu `/home`, not Windows `/mnt/c`, for Linux filesystem semantics and performance.

### Step 4 — check dependency availability in an isolated Python environment

```bash
python3 -m venv ~/p0a-work/venv
source ~/p0a-work/venv/bin/activate
python --version
python -m pip --isolated install pip==25.0.1
python -m pip --isolated install --dry-run -r ~/p0a-work/PropertyAIgent/verification/p0a-python-environment.txt
```

**Checkpoint:** pip resolves the exact pins for this Python without errors. This downloads package metadata and may download wheels; it runs no application tests or paid model calls. Some snapshot pins have not been independently verified against public PyPI here. If a version is unavailable or Python is rejected, stop and send the error. Do not upgrade to unpinned replacements.

### Step 5 — install and verify those exact packages

```bash
python -m pip --isolated install -r ~/p0a-work/PropertyAIgent/verification/p0a-python-environment.txt
python -m pip check
python -m pip list --format=freeze > ~/p0a-work/actual-dependencies.txt
diff -u ~/p0a-work/PropertyAIgent/verification/p0a-python-environment.txt ~/p0a-work/actual-dependencies.txt
```

**Checkpoint:** `pip check` reports no broken requirements; diff has no output. The runner also enforces this comparison. Return any difference rather than editing the snapshot. All Python packages are in `~/p0a-work/venv`; Ubuntu's system Python is unchanged.

### Step 6 — install matching Chromium and Linux browser libraries

```bash
export PLAYWRIGHT_BROWSERS_PATH="$HOME/p0a-work/browsers"
python -m playwright install --with-deps chromium
```

**Checkpoint:** download and dependency installation succeed. This may request sudo for Ubuntu libraries; Chromium is downloaded for your normal user. Use the pinned Playwright installer, not an unrelated Ubuntu Chromium package. If installation fails, send its error before another attempt.

### Step 7 — check that no production inputs will be used

Run from Ubuntu, before launching the isolated test:

```bash
compgen -e | grep -E '^(DATABASE_URL$|RENDER|OPENAI|ANTHROPIC|SUPABASE|PG|PROPERTYAIGENT_|P0A_TEST_POSTGRES_URL$)' || true
for p in "$HOME/p0a-work/PropertyAIgent" "$HOME/p0a-work" "$HOME" /home /; do
  if [ -e "$p/.env" ]; then printf 'STOP: .env exists at %s\n' "$p"; fi
done
```

**Checkpoint:** neither check prints anything. These commands show variable names only, never values. If an input/file is present, stop; do not display its contents or delete another project's files. The wrapper and runner repeat the checks before application imports/DB creation. The wrapper additionally passes a clean, allowlisted environment to tests. Never create `.env` or add a production URL/API key for these tests.

### Step 8 — run the isolated verification

```bash
bash ~/p0a-handoff/p0a-wsl-run.sh
```

The wrapper uses sudo only to create temporary private mount/network/PID namespaces, turns on only loopback there, and starts a process reaper. It then drops back to your normal user before PostgreSQL or tests. It does not disable your laptop's internet or change host mounts. Chromium and DB operate inside this isolation; no council or paid API is reachable. No Docker or cloud service is needed.

**Checkpoint:** if WSL denies namespace/mount creation, stop and return the console error. Do not bypass the network or root checks. The wrapper packages available logs even on failure. It must not be described as tested on WSL until it actually runs successfully there.

The original runner creates a fresh `p0a_test_gate_a` database in its own temporary PostgreSQL cluster, rejects nonempty/non-loopback test targets, runs candidate and matched baseline, and stops its cluster afterwards. It never connects to Ubuntu's default cluster, Supabase or Render. A nonzero exit may reflect the known baseline failures; it is not permission to ignore failures.

### Step 9 — return evidence

The final console line identifies a file similar to:

`/home/maxrose26/p0a-work/results-20260929T090000Z.tar.gz`

```bash
explorer.exe "$(wslpath -w ~/p0a-work)"
```

Attach that exact `results-...tar.gz` file to this chat. It contains the console, available candidate/baseline logs/XML, runtime/dependency/commit manifests and exit code. If no archive was produced, paste the first failing command and its error, without secrets. I will assess/fix within scope and keep the review loop here; you do not need to relay every correction to another chat.

Gate A remains open until actual PostgreSQL, Chromium and ownership checks pass and candidate-specific failures are resolved. Direct PostgreSQL is not production transaction-pooler evidence. No push, deployment, live scrape or production migration is part of this guide.

## Official references

- Python virtual environments: https://docs.python.org/3.12/tutorial/venv.html
- Python ABI stability within a minor release: https://docs.python.org/3.12/c-api/stable.html
- Playwright browser/dependency installation: https://playwright.dev/python/docs/browsers
- WSL Linux filesystem guidance: https://learn.microsoft.com/en-us/windows/wsl/filesystems
- Linux namespace command semantics: https://man7.org/linux/man-pages/man1/unshare.1.html
