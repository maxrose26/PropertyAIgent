"""Record-level screening of a partial observation (specification 033). The record-level screen is window-independent, so the SAME pure function is reused unchanged; this wrapper only adds provenance and
refuses anything that is not an observation. It writes nothing, claims no window completeness and creates no coverage."""
from .ledger import Denied,digest
from .listing_screening import screen_row
from .idox_adapter import OBSERVATION_KIND,OBSERVATION_WINDOW_CLAIM


def screen_observation(observation):
    if observation.get('kind')!=OBSERVATION_KIND or observation.get('window_claim')!=OBSERVATION_WINDOW_CLAIM:raise Denied('OBSERVATION_REQUIRED')
    evidence_digest=digest(observation)
    return [dict(reference=r['reference'],screen=screen_row(r),provenance=dict(source_kind=OBSERVATION_KIND,window_claim=OBSERVATION_WINDOW_CLAIM,observation_digest=evidence_digest,
                                                                            observed_at=observation['observed_at'],record_digest=digest(r)))
            for r in observation['records']]
