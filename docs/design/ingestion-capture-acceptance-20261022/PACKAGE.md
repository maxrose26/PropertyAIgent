# Bolton capture acceptance (22 October) - package

Preparation only; `execution_authority: NONE`. Implements specification 032 section 13.

| File | Purpose |
|---|---|
| `policy-capture-allowance.sql` | policy v4, derived mechanically from v3 (three changed lines) |
| `render_registration.py` | offline renderer: `--mode policy` then `--mode capture` (needs the policy ceremony's audit hashes and final control digest) |
| `owner-run-policy.sh`, `owner-run-capture.sh` | the two owner-local ceremonies (visible WSL terminal; the credential only at the hidden prompt) |
| `base_constants.json`, `MANIFEST.json` | carried non-secret constants; the bound file list |

Restricted half: `.github/workflows/stage4-capture-acceptance-once.yml` -> `verification/ingestion_storage/capture_acceptance.py` (the accepted stable pipeline under this mode's identity).

Order: policy ceremony -> capture ceremony (Claude dispatches the restricted job once the capture allowance is recorded; the owner approves the protected environment). One run each; nothing is retried or replaced automatically.
