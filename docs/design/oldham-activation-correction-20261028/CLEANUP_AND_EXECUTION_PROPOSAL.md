# Consolidated cleanup and installed-policy execution

The prior identified reuse gap is implemented in this same draft PR by explicit
OLDHAM_CAPTURE_SCREENING_INSTALLED_V1. No detection/fallback selects it. Initial
OLDHAM_CAPTURE_SCREENING_V1 retains its retirement/install behavior unchanged.

See OWNER_HANDOFF.md for exact cleanup and fresh-execution phases, original-file
requirements, isolated command, limits and later attended authority. Both phases
share the existing owner clock/counters; no separate unmeasured allowance is added.
Private originals and production state must not be invented. The delivery is
INACTIVE: no credential, connection, expiry, grant or processing is authorised.
