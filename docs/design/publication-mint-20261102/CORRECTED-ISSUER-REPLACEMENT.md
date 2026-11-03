# Fixed corrected-issuer replacement — INACTIVE / 3 November only

Prior owner d3085a0 and every historical file remain unchanged in their original
checkout. App/client binding differs only at Client-ID character5, I→l.
Corrected raw authority28a039e7… / canonical ed07a6fb… is fixed. Required public
proof is corrected GET resultf9b43000…: HTTP200, installation MATCH, oneGET,
zeroPOSTs, normal closure. This proves corrected authentication NOW, not the
unrecorded cause of the original HTTP refusal.

Explicit --replace-issuer-refusal selects only ONE mint replacement after exact
prior resultccbff66a… (HTTP/DEFINITELY_NOT_SENT, child exit2/closed). Preserve original
authority a10aa38e…, original marker691860d9…, journal147b832c…, pre-child refusal
233a2cc3… and diagnostic receipts/source evidence. Do not delete, modify or reuse
them. Exact hashes are checked before owner input, after input and in the child.

Before consuming new authority, the existing B-state Vault passphrase must decrypt
the ORIGINAL journal locally. Require its exact five-field shape, original bound
authority, state REFUSED_POST_NOT_SENT and post_started=false; no token/receipt.
Other state, mismatch or uncertainty refuses, never another POST. Decryption is
read-only. The SAME authenticated Vault passphrase encrypts the new journal; no
new credential or confirmation prompt is needed. Same signing key/fingerprint,
App5577857/installation177784553/repository1317423499, Contentswrite/Metadataread.

Fixed new private paths under the existing0700 App root:
- mint-evidence-corrected-client-id-01 (terminal result only)
- mint-corrected-client-id-01-consumed.json (exclusive fsynced one-use marker)
- mint-corrected-client-id-01.vault (existing encrypted journal)
- mint-corrected-client-id-01.vault.next (existing atomic-save temporary)

The original and corrected entry points refuse new/prior marker/journal reuse.
The new exclusive marker precedes any network work. Existing GET validation,
fsynced POST_INTENT, onePOST/no retries, response validation/token encryption,
cleanup,60s/4096-byte capture/2048-byte result, TLS and4000-byte secret frame stay.
No failed/uncertain child result authorises another slot or attempt.

This prepares mint only, not sealing or later phases. A future separately approved
seal reads the corrected journal only for the exact corrected canonical authority;
all seal/window/target bindings and the single publication-01.vault remain intact.
Existing later owner clients still use the SAME Vault passphrase. No new controller,
secret store, dependency, application or SQL/Render operation is introduced.

Before mint, confirm availability for the complete approximately one-hour owner
session, including about25minutes ageing and eventual independently approved
closure. Confirm execution day3November2026: current seven-day window27October–
2November inclusive, Tameside RECEIVED/Manchester VALIDATED. Do not roll dates.
A fixed local day gate refuses another day or <=3065seconds before next midnight;
actual expiry guards remain E-2100<=seal/open<E-1445, submission life>1145seconds,
and period expiry<=min(E,next London midnight). No expiry is fabricated. If any
remaining review/manual delay consumes the margin, stop/contain rather than rush.
