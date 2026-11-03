# One successor after EXPIRED_UNUSED — INACTIVE; existing App/key retained

No prior record is reset. The exact corrected mint result9e204657… and receipt
2e4ec546… expire2026-11-03T10:56:24Z. A separate, exclusive local closure record
must be made AFTER actual expiry, showing EXPIRED_UNUSED, no later phase evidence,
no token-specific revocation and no installation removal. Exact closure hash,
unchanged predecessor ciphertext/marker and all old authority/refusal/diagnostic
hashes are required by the successor. Before new intent the owner must locally
decrypt the predecessor: exact validated/unarmed receipt2e4ec546…, same authority,
actual expired E, no seal binding, retainable token. Never print/decrypt via Codex.

Fixed new one-use names below the existing private App root:
mint-expired-unused-successor-01-consumed.json;
mint-expired-unused-successor-01.vault / its existing .next temporary;
mint-evidence-expired-unused-successor-01/result.json.
All old and new mint entry points refuse a consumed successor. New marker binds
the exact predecessor receipt and closure hashes. Prior expiry is a necessary
precondition: no overlap with that live token, no automatic renewal or POST retry.
Only one explicit separately approved successor is provided. Any new failure or
uncertainty consumes it; there is no looping attempt factory or new controller.

Same App5577857/installation177784553/repo1317423499, corrected Client ID, existing
signer/key/fingerprint and Contentswrite/Metadataread scope. Existing Vault,
transport, receipt validation,60s/4096-byte capture/2048-byte public result,
4000-byte anonymous secret frame, timeouts/TLS/zero retries and closure remain.
Explicit --successor-expired-unused selects the new journal for mint AND future
local seal, never silently selecting another receipt with the same authority.
No activation, SQL, handoff or job occurs through this helper.

Existing static release facts/commands live in b-successor-release-20261103.
Pure local finite_release_binding check validates them using a synthetic public
receipt. preview uses the next actual public mint receipt during ageing and
creates a non-executable review record, with no fresh observation. Only after
review/approval and valid E-2100<=now<E-1445, freeze prompts for a JUST-CHECKED
owner observation. Its actual confirmation time is captured immediately and
binding/policy/hash files are written immediately, not after documentation work.
No network, credential, Vault read, automatic phase or provider mutation is added
by this binding utility. Preview/freeze files are exclusive and never overwrite.

Execution day is fixed3November2026; window27October–2November inclusive,
Tameside RECEIVED/Manchester VALIDATED. Another date requires explicit rebinding,
never clock manipulation. Existing E/midnight/submission/300s freshness guards
remain. Token-dependent work must complete within actual expiry; reserve75–90min
owner availability for the whole session including post-closure readbacks, not
75–90min of token lifetime. No build/A/qualification/stop/recovery repetition.
