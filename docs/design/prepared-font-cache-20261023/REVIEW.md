# Default-off prepared fontconfig cache — offline candidate

Aim: stop the probe's Chromium from rescanning every system font on each run, while
preserving font selection, fresh-HOME isolation and the unchanged memory limits. Stage 4
remains OPEN; live execution remains NO-GO. No registration, permit or live run is created.

Baseline: master `151351be2f21dfc61b73f0bbc1bc44c55c5384fd`.

## Problem (measured offline)
`chrome-headless-shell` statically bundles fontconfig (`cache-11`) and cannot use the system
fontconfig 2.15 caches (`cache-9`). Its only writable cachedir is the fresh per-run
`$HOME/.cache/fontconfig`, so every run rescans `/usr/share/fonts` and rebuilds about 20 cache
files. On a cold page cache that charged about 173MiB of file cache to the 1GiB source group.

## Change
* **Default unchanged.** Without an explicit selection, nothing new runs. The launch call is
  `chromium.launch(headless=True)` with no extra options, and the child command and environment
  are identical.
* **Explicit prepared mode.** It is selected only by passing both a cache directory and the SHA256
  of its `MANIFEST.json`:
  `supervised(..., prepared_font_cache=(dir, sha256))` → probe flags
  `--prepared-font-cache DIR --prepared-font-cache-sha256 HEX` (both or neither). Unsupported
  worker modules refuse. No registration is changed here; binding a release registration to a
  manifest is deferred until a live registration is proposed.
* **Validation before launch, so before navigation, inside the probe worker (source cgroup).**
  The probe refuses with a fixed code and starts no browser:
  `PREPARED_FONT_CACHE_MISSING`, `…_MANIFEST_MISMATCH`, `…_STALE`, `…_INVALID` or `…_UNVERIFIED`.
  There is no fallback.
  * **Trusted system ancestors:** real directories owned by root or this user. Shared ones must be
    sticky. No symlinks.
  * **Controlled cache:** owned by this user, read-only, regular, single-link files named
    `<32 hex>-le64.cache-11` or `CACHEDIR.TAG`, plus the manifest. The exact file set and every
    file's SHA256 must match.
  * **Bounded invalidation inputs:**
    * browser identity: the headless-shell revision from Playwright's `browsers.json`, resolved
      under `PLAYWRIGHT_BROWSERS_PATH`, with executable size and mtime
      (`chromium.executable_path` names the full Chromium build, which headless launches do not run);
    * a font-directory listing (path, size, mtime);
    * `fonts.conf`, `local.conf`, and the `conf.d` names, link targets and contents;
    * the derived config hash.
  * **Limits:** manifest 256KiB, 1MiB per config file, 256 `conf.d` entries, 20,000 font entries,
    512 cache files, 64MiB of cache.
* **Browser-only environment.** The caller's environment plus exactly one variable,
  `FONTCONFIG_FILE`. It names a per-run copy (mode 0400, in the fresh HOME) of the system
  `fonts.conf` with only its `<cachedir>` elements replaced by the read-only prepared directory,
  and the relative `conf.d` include made absolute. All rules are kept verbatim, and there is no
  writable cachedir.
* **Preparation (`prepare()`) is for development and tests only.** It creates a new empty
  directory, renders once, then seals and verifies it. There is no persistent owner-cache
  installation and no system-wide configuration.

## Evidence (separated)
* **Functional cache-use proof:** `tests/test_prepared_font_cache_browser.py`, real Chromium,
  council-free, skipped without a browser. Font selection is identical to default mode for 9
  representative samples (platform fonts, glyph counts, boxes). Prepared cache files are mapped
  from the prepared directory. An `FC_DEBUG=16` trace shows cache loads with no scan or write.
  Nothing is written to the per-run HOME, while default mode rebuilds.
* **Memory evidence:** the native `real-chromium` fixture (real `Source.run` → worker → production
  `supervised()` pass-through → browser child using production `browser_launch_options()`), with
  read-only `mincore` residency classified before each run (COLD: every set ≤2% resident; WARM:
  every set ≥90%; otherwise PARTIAL). Without qualified COLD pairs the numerical saving stays
  unproven.

## Held
No merge, registration, permit, live execution, deployment, system-wide or persistent cache, or
dependency change. Memory limits and failure policy are unchanged. Local memory-pressure,
deliberate cache-eviction and forced-reboot tests remain paused.
