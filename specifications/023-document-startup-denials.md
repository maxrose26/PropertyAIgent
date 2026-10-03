# Document renderer startup denial contract

This is a finite fatality-classification correction, not native transport permission.
The kernel-facing response remains EPERM with no seccomp CONTINUE flag.

Only digest-verified Chrome Headless Shell 153.0.8010.12 (SHA-256
`ded93a9c9a53a1ae040f08124badcca95c938e9d5015ff340c3b5538c41bf39e`)
may receive nonfatal handling for these x86-64 socket calls, at most once each:

| Family | Exact type/flags | Protocol |
| --- | --- | --- |
| AF_NETLINK (16) | SOCK_RAW (3) | NETLINK_ROUTE (0) |
| AF_NETLINK (16) | SOCK_RAW + SOCK_CLOEXEC + SOCK_NONBLOCK (526339) | NETLINK_KOBJECT_UEVENT (15) |

No masking admits additional flags or protocols. The notifying thread must belong
to the original owned root process, with matching TGID, start identity, parent,
process group and verified executable device/inode/metadata. Descendant membership
or an executable filename alone is insufficient. Identity uncertainty is fatal.

The startup phase closes irreversibly before forwarding any browser response/event
bytes, any command other than the first Browser.getVersion, or a second command.
Repeated probes, later probes, different protocols/types and wrong processes retain
fatal denial. AF_UNIX retains its pre-existing direct EPERM handling. Other native
filter rules, limits, authentication, HTTP transport and cleanup remain unchanged.

Each special denial is audited with process/thread/start identity, tuple, phase and
EPERM result only after the denial response succeeds. Unknown runtime digests retain
fatal denial; a runtime upgrade requires new compatibility/security review.

Disposable characterization observed the pair in 44 root lifetimes before the first
browser response and completed 22 document checks. ROUTE interface tracking and
UEVENT device monitoring are corroborated subsystem inferences, not exact pinned
call-stack attribution. No supported avoidance was established. This observation is
not final acceptance: real denial negatives, the complete exact-candidate renderer
pack and independent security review remain required.

Existing launch flags are preserved, including --no-sandbox. This correction does
not claim Chromium's internal sandbox is enabled; the existing external seccomp,
private transport and process ownership controls form this containment boundary.
Publication, merge and production release remain separate decisions.
