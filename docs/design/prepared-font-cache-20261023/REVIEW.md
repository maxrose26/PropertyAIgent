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
* **Structural refusals (INVALID).** The mode only covers what it fingerprints. It refuses when
  any of the following holds:
  * `conf.d` or `local.conf` adds a `<cachedir>` or an absolute `<dir>`;
  * the absolute `<dir>` set in `fonts.conf` differs from the fingerprinted font directories;
  * a per-run config already exists.
  Without these refusals, a rescan of an unfingerprinted directory would be a silent fallback.
  `verify()` also checks the exact derived-config bytes handed to the browser against the
  manifest.
* **Dependency coverage (no general configuration framework).**
  * **Font file symlinks** (15 on the reference host, some through `/etc/alternatives`) are
    recorded with link text, resolved path and the target's size and mtime, so a retargeted or
    replaced target is STALE. Symlinked font directories are INVALID. Unreadable directories and
    dangling links are UNVERIFIED.
  * **Includes and font dirs are an exact whole-element allowlist:**
    * `fonts.conf`: only the relative `conf.d` include, plus the fingerprinted absolute font
      dirs and the two per-user dirs (`prefix="xdg"` fonts, `~/.fonts`).
    * `conf.d`: only the five reference-host includes (`local.conf` and four per-user forms),
      and no `<dir>`.
    * `local.conf`: no include and no dir.
    Every `<include` and `<dir` occurrence must be one of these exact elements. Any CDATA or
    entity declaration, any `<remap-dir>` (adds a font directory) or `<reset-dirs>`, and any
    configuration file that is not plain UTF-8 (NUL bytes, a byte-order mark, invalid bytes) is
    refused. So `..` escapes, forged attributes, and CDATA, comment-split
    or entity-built values are INVALID. `conf.d` and `local.conf` are content-hashed, so an
    included file changing under an unchanged parent is STALE.
  * **Per-user locations:** these resolve into the fresh per-run HOME. At launch, prepared mode
    refuses (INVALID) if any per-user font or config path exists there, or if an environment
    variable that redirects fontconfig (`FONTCONFIG_PATH`/`SYSROOT`, `XDG_*`) is set.
    `supervised()` sets none of them.
* **No default-path dependency.** The new module is imported only in prepared mode. The Render
  disposable job ships only `instrumented_probe.py` and `arcus_http_probe.py`, and default mode
  must not need anything else.
* **Preparation (`prepare()`) is for development and tests only.** It rescans every font, so it
  warms the page cache outside any measured boundary; later runs are classified by measured
  residency, never assumed cold. It creates a new empty
  directory, renders once, then seals and verifies it. There is no persistent owner-cache
  installation and no system-wide configuration.

## Evidence (separated)
* **Functional cache-use proof:** `tests/test_prepared_font_cache_browser.py`, real Chromium,
  council-free, skipped without a browser. Font selection is identical to default mode for 9
  representative samples (platform fonts, glyph counts, boxes). Prepared cache files are mapped
  from the prepared directory. An `FC_DEBUG=16` trace shows cache loads with no scan or write.
  Nothing is written to the per-run HOME, while default mode rebuilds. A positive control shows
  the same `FC_DEBUG=144` trace printing `FcDirCacheWriteDir` in default mode. The `/proc` maps
  scan covers only the run's own browser processes.
* **Memory evidence:** the native `real-chromium` fixture (real `Source.run` → worker → production
  `supervised()` pass-through → browser child using production `browser_launch_options()`), with
  read-only `mincore` residency taken before each run, with explicit coverage (files, measured,
  failed, coverage and errors per set). The classes are:
  * COLD: every set completely measured and at most 2% resident;
  * WARM: completely measured and every set at least 90%;
  * PARTIAL: completely measured otherwise;
  * INCOMPLETE: any missing root, empty set, walk error, unreadable file or failed measurement.
  INCOMPLETE is never COLD. Without qualified COLD pairs the numerical saving stays unproven.

## Readers sharing this launch path
Only `instrumented_probe.probe()` uses it. It is reached through `supervised()` for 87 cases on
four Arcus/Salesforce-style portals: Manchester (38), Salford (25), Rochdale (23) and Trafford (1).
These include the Arcus UI-window listing cases reached via `finite_acceptance.read()`. Prepared
mode is available there only by passing `prepared_font_cache=` to `supervised()`. Plumbing it
through `finite.read()` and the source-release launcher, and binding it to a registration, is
deferred and needs separate review.

Not on this path:
* Idox readers (Bury, Tameside, Oldham), `narrow_oldham_source`, `r0_bolton53`, `r0_fixed80` and
  `material_qualification` use no browser.
* The production weekly pipeline (`app/pipeline/run_weekly.py`, whose pages `app/scrapers/*` and
  `app/ingestion/listing_screening.py` use) launches its own browser, as do the standalone
  checks: `verification/stage1_*`, `spec028`, `b21`, `scripts/diagnose_browser_memory.py` and
  `scripts/verify_browser_runtime.py`. Each would need separate wiring and qualification.
* `render_disposable_job.py` calls `supervised('trafford')` in default mode only. On master it
  already cannot import the probe from its two-file payload; that is pre-existing.

## Held
No merge, registration, permit, live execution, deployment, system-wide or persistent cache, or
dependency change. Memory limits and failure policy are unchanged. Local memory-pressure,
deliberate cache-eviction and forced-reboot tests remain paused.
