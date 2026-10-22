# Open decision: permanent retention policy for retained captures, observations and screening results

Status: **UNRESOLVED (recorded 21 Oct 2026).** Not decided by any specification, test or code.

**Facts.** Behaviour exists without a written policy: the raw capture archive is committed to the evidence branch (no deletion path); ledger checkpoints and screening results have no pruning procedure; CI run artifacts are kept for each workflow's configured days; the only retention statements elsewhere (full historic retention for monitored reports; "log level, retention and access remain rollout prerequisites", specification 021) do not cover captures.

**Interim rule until decided:** preserve all current evidence. No pruning, expiry or deletion path is added by any phase of specifications 033 or 034; observations inherit exactly the capture behaviour.

**Questions for the product owner:** duration per evidence class (raw archive, ledger records, observations, derived screening results, sealed run artifacts); whether anything may ever be pruned; treatment of derived results when raw evidence is removed; personal-data considerations of site addresses in listing text; who may authorise deletion.
