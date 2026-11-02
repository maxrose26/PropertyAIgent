# Owner-local publication mint/seal — INACTIVE

Base owner99309a2fa072f52eb02884975008f8a2a75f792b; applicationdb05f5d frozen.
No App or installation exists for this proposal yet. Actual App/client/installation
IDs and public-key fingerprint must be reviewed in a nonsecret authority file;
template nulls deliberately refuse. No source/DB/Render operation is implemented.

Fixed accountmaxrose26, repositoryPropertyAIgent/id1317423499, private App slug
propertyaigent-b-maxrose26, Contents write/Metadata read only. One fixed attempt
ONE_B_PUBLICATION_TOKEN_MINT_V1; paths fixed below the private0700 directory
/home/maxrose26/.local/share/propertyaigent/b-publication-app. Keysigning-key.pem,
mint-01.vault, mint-01-consumed.json, seal-01-consumed.json, publication-01.vault,
mint-evidence-01, seal-evidence-01. No configurable target/permission/URL/path,
renewal, second attempt or automatic revoke. Root/key owner checks/no links,
encrypted PEM max64KiB/fingerprint bound; hidden passphrases. Existing Vault32KiB
and opaque token validator are reused; no new dependency. Private vaults are not
public evidence and must never be packaged. Public result/stdout each≤2048bytes.

Mint: exclusive fsynced attempt and encrypted baseline before work; local RS256
JWT with actual client-ID issuer/iatnow-60/expnow+300, signing key stays local.
One fixed installationGET checks exact App/installation/account/permissions,
selected repositories and unsuspended state. Fsynced POST_INTENT precedes at
most one fixedPOST/repository_ids+permissions body. Fresh requests session,
trust_envfalse, zero retries/redirects, verified direct TLS/api.github.com443,
5s connect/read timeouts,32KiB per response. Existing owner capture enforces the
60s child envelope (TERM at58s/KILL at59s),4096-byte raw child-output cap,
and anonymous secret input≤4000bytes; no secrets in args/environment. Prompts
are outside the active envelope. Raw child output is never retained: only its
strictly allowlisted≤2048-byte result and bounded process status are saved. GET is
before POST; any exception after entering POST is uncertain, including a timeout.
Live caught pre-POST failure is definitely unsent FOR THIS INVOCATION. Existing
attempt refuses and never reclassifies the earlier attempt. An interrupted
POST_INTENT without an acknowledgement remains uncertain, even if send is unproven.

Require201, strict duplicate-free JSON, compatible opaque token, exact returned
one-repository identity/permission set/selected mode and actual RFC3339UTC expiry.
Received token candidate encrypted before scope/expiry checks; no response body,
JWT, key, headers or exception text exported. Receipt is an allowlisted projection
with actual scope/expiry/time; no JWT decoding. Provider expiry must exceed the
remaining preparation/B/closure window and lie within the documented one-hour
lifetime plus60s local clock tolerance. Wall/monotonic divergence>5s refuses.
Failed/unretainable/malformed scope or acknowledgement needs closure, never a
replacementPOST. Session close failure also refuses. No secure memory-erasure
claim; the restricted owner process exits after each phase.

Seal: entirely local; source receipt/authority/hash/state must match, exact final
owner binding uses actual expiry for publication_valid_until AND valid_until and
binds publication_mint={authority_sha256,receipt_sha256,expires_at}. Its token vault
path is fixed. At seal/opening, unchanged960<remaining≤2100 limit still applies;
new mint bindings additionally require remaining>1445s: five60s remaining owner/
preflight phases +960s B +5s external grace +three60s closure phases. This is a
conservative latest-start restriction, not a larger runtime/expiry budget. Same
guard runs before activation connection and against server clock before temporary
owner entry. Existing bindings without mint metadata retain original behaviour.
Period/opening guards reject late starts; diagnostics retain the two new literal
mint binding/window codes. No activation is performed by this helper.

Fresh one-hour token waits approximately25minutes until remaining≤35minutes.
Seal/open within E-2100≤now<E-1445 (E=actual returned expiry). No wait is performed
inside a60s phase. Up to300s is allocated to remaining owner/preflight work;
manual delay must be reassessed. At actual B submission require remaining>1145s
(960+5+180) or contain and stop, not submit. Never reduce reserve by declaring
phases faster or spend the closure allowance on collection. This offline helper
cannot prove future provider/job timing; the existing ordered owner ceremony
must enforce the pre-submission check. B runtime/period budgets remain unchanged.

Exclusive seal intent precedes target creation. Existing token_arm/token_load
write/read the exact token in the existing publication vault, then source token
candidate is withdrawn and seal acknowledged. Mid-seal/write/lost-ack failure
consumes seal, preserves both files and refuses; never retry seal or delete paths.
A valid target vault can be independently revoked through existing owner client
and exact binding (one204, intent beforeDELETE, no repeat on uncertainty). DB
containment does not depend on token closure or restoration.

Before a valid target exists, invalid scope, missing token or unretainable reply
cannot be made revocable by weakening token_arm. Approved owner UI uninstall of
this exact new installation is the supported containment alternative, followed
by separate issuer retirement; it is not a token-specific204 receipt. Pending
UI closure must be approved/readied before any real mint. Expired≠revoked.
Key deletion alone is not installation containment. Preserve all intent files.

Validation uses only synthetic encryptedRSA keys/tokens, temporary private paths,
mocked HTTP/session/activation surfaces. No provider transport is used live and
no real key is accessed. Previous PG17, CLI hosted proof and council suites are
retained, not repeated. Source helper is local preparation, not Render code.
