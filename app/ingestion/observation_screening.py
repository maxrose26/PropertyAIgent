"""Record-level screening of a partial observation (specification 033). The record-level screen is window-independent, so the SAME pure function is reused unchanged; this wrapper only adds provenance and
refuses anything that is not an observation. It writes nothing, claims no window completeness and creates no coverage."""
from .ledger import Denied,digest
from .listing_screening import screen_row
from .idox_adapter import OBSERVATION_KIND,OBSERVATION_WINDOW_CLAIM


def observation_revision(revision, observation_sha256):
    """Scope a task to immutable observation evidence, not a new screening rule."""
    import re
    if not re.fullmatch('[a-f0-9]{64}', str(observation_sha256)):
        raise Denied('OBSERVATION_DIGEST_REQUIRED')
    return digest(dict(assessment_revision=revision, observation_sha256=observation_sha256))


def require_enabled(councils, council):
    # Trusted controller selection and SQL grant selection are independent gates.
    if councils != ('bolton',) or council != 'bolton':
        raise Denied('PARTIAL_OBSERVATION_NOT_ENABLED')


def screen_observation(observation):
    if observation.get('kind')!=OBSERVATION_KIND or observation.get('window_claim')!=OBSERVATION_WINDOW_CLAIM:raise Denied('OBSERVATION_REQUIRED')
    evidence_digest=digest(observation)
    return [dict(reference=r['reference'],screen=screen_row(r),provenance=dict(source_kind=OBSERVATION_KIND,window_claim=OBSERVATION_WINDOW_CLAIM,observation_digest=evidence_digest,
                                                                            observed_at=observation['observed_at'],record_digest=digest(r)))
            for r in observation['records']]


def retained_history(ledger, keys):
    """Bounded read projection of immutable checkpoints; no alternate history store."""
    from .observation_history import empty_history,append,_utc
    if len(keys)>74 or len(set(keys))!=len(keys):raise Denied('HISTORY_READ_BOUND')
    evidence=[]
    for key in keys:
        row=ledger.get(key);value=row['checkpoint']
        if row['task']!='DISCOVERY' or row['state']!='COMPLETE' or value.get('kind')!=OBSERVATION_KIND:
            raise Denied('OBSERVATION_CHECKPOINT_REQUIRED')
        evidence.append(value)
    history=empty_history()
    for value in sorted(evidence,key=lambda v:(_utc(v['observed_at']),digest(v))):history=append(history,value)
    return history
