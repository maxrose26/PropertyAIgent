# Bolton window demonstration (23 October) - package

Preparation only; `execution_authority: NONE`. Implements specification 032 section 14: ONE complete-window demonstration for Bolton RECEIVED 2026-09-28 to 2026-10-04 under the unchanged completeness contract and ceilings.

| File | Purpose |
|---|---|
| `policy-window-allowance.sql` | policy v5, derived mechanically from v4 (generation 3, one exact scope, two named allowances) |
| `render_registration.py` | offline renderer: `--mode policy` then `--mode window` (needs the policy ceremony's audit hashes and final control digest) |
| `owner-run-policy.sh`, `owner-run-window.sh` | the two owner-local ceremonies (visible WSL terminal; the credential only at the hidden prompt) |
| `base_constants.json`, `MANIFEST.json` | carried non-secret constants; the bound file list |

Restricted half: `.github/workflows/stage4-window-demonstration-once.yml` -> `verification/ingestion_storage/window_demonstration.py` (the accepted stable pipeline under this mode's identity and scope).

Order: policy ceremony (it first observes and verifies the derived generation-3 state) -> window ceremony (Claude dispatches the restricted job once the capture allowance is recorded; the owner approves the protected environment). One run each; nothing is retried or replaced automatically.
