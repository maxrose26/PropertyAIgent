# Narrow-correction verification handoff

This is offline verification, not release approval. Use the previously prepared
non-production Ubuntu24.04 WSL2 account and existing pinned Python3.12.3 venv,
PostgreSQL16 and matching Playwright Chromium. No production inputs or .env.
No new package installation is required by this handoff.

1. Download **p0a-narrow-corrections.bundle** and its SHA256 file from the chat.
   Put both in `/home/maxrose26/p0a-handoff/` (your WSL home, not this remote workspace).
   Run `cd ~/p0a-handoff && sha256sum -c p0a-narrow-corrections.sha256`.
   Stop unless it says OK.
2. In `~/p0a-work/PropertyAIgent`, check `git status --short` is empty; preserve
   any local edits rather than resetting them. Fetch the bundle's
   `refs/heads/feature/p0a-bounded-discovery`, then detach at the exact full SHA
   supplied in the chat. Check `git rev-parse HEAD` matches and status is empty.
3. Run `bash verification/p0a-wsl-run.sh FULL_CANDIDATE_SHA` from that checkout.
   The launcher now requires the SHA argument. It verifies the new runner blob,
   dependencies, clean tree, absence of production env/.env, and creates local-only
   UTF8 PostgreSQL within the already tested network/PID/mount isolation.
4. Return the results archive named at completion. Exit1 is expected if the same
   four historical failures remain, but is never itself evidence of acceptance.
   New migration/bounds/ownership tests must pass without skips. No production
   password is needed. The baseline is fixed at301a56b3cde781f37e5f5bb0ffaded6537d5ca14.

The new tests include a real15s statement timeout; allow the runner to finish.
Keep candidate/baseline logs/XML, exact SHA, runner blob, dependency and database
encoding records together. Do not run the migration command against Supabase.
Do not change the production scheduler to verify this candidate.
