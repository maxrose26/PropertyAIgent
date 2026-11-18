"""One proposed continuation from the exact contained deployment; inactive until accepted.

Counters never reset. New cleanup starts from its last durable normal state,
while the prior cleanup baseline remains independently addressable in row34.
"""
import copy
import hashlib
from .tameside_preparation import require

CHECKPOINT='fe492bc56569239083643df8e9f0e2304965e545fe3f54ec2a32e491c84bdac5'
DEPLOYMENT='dep-dbukble7bikc73a7jad0'
FIELD='contained_continuation'
RELEASE_ROOT='/tmp/pa-tam002-contained-01'
USED=7


def start(journal,state,approval_ref,review_ref):
    require(journal.ordinal==34 and journal.previous==CHECKPOINT,'CONTAINED_CHECKPOINT')
    require(state.get('status')=='PREPARATION_CONTAINED_NO_SUBMISSION' and FIELD not in state,'CONTAINED_ONCE')
    require(state['cleanup_reserve']['cleanup_writes']==USED,'CONTAINED_CLEANUP_ACCOUNTING')
    require(not any(k in state for k in ('access','job','independent_result')),'CONTAINED_NO_SUBMISSION')
    require(not any(k.startswith('STOP15_') and not k.startswith('STOP15_REPLACEMENT_') for k in state['intents']),'CONTAINED_NO_RELEASE')
    require(state['intents']['STOP15_REPLACEMENT_ONE_RESUME_BUILD']['state']=='INTENT','CONTAINED_ORIGINAL_INTENT')
    require(approval_ref!=state['continuation']['approval_ref'] and review_ref!=state['continuation']['review_ref'],'CONTAINED_NEW_ACCEPTANCE_REQUIRED')
    require(all(state['intents'].get(k,{}).get('state')=='ACKNOWLEDGED' for k in ('CONTAIN_SUSPEND','CONTAIN_STOP15_REPLACEMENT_RESTORE_BUILD_CONFIGURATION','CONTAIN_STOP15_REPLACEMENT_RESTORE_BUILD_ENVIRONMENT')),'CONTAINED_RESTORATION')


def admit(runner):
    from .tameside_stop15 import canonical
    r=runner.state['cleanup_reserve']
    runner.state[FIELD]=dict(version='CONTAINED_ROW34_V1',ordinal=34,sha256=CHECKPOINT,
        deployment=DEPLOYMENT,cleanup_used=USED,old_cleanup_base_bytes=r['cleanup_base_bytes'],
        old_cleanup_base_access_bytes=r['cleanup_base_access_bytes'],
        elapsed_bound_at=runner.state['bound_at'],elapsed_binding_sha256=hashlib.sha256(canonical(runner.state['binding'])).hexdigest(),
        approval_ref=runner.approval_ref,review_ref=runner.review_ref,phase='NORMAL')
    runner.journal.cleanup_mode=False


def identity(marker):
    return isinstance(marker,dict) and marker.get('version')=='CONTAINED_ROW34_V1' and marker.get('ordinal')==34 and marker.get('sha256')==CHECKPOINT and marker.get('deployment')==DEPLOYMENT and marker.get('cleanup_used')==USED


def normal_allowed(journal,state):
    marker=state.get(FIELD);prior=(journal.state or {}).get(FIELD)
    if not identity(marker) or marker.get('phase')!='NORMAL':return False
    if prior is None:
        if journal.ordinal!=34 or journal.previous!=CHECKPOINT:return False
    elif marker!=prior:return False
    return state['cleanup_reserve']['cleanup_writes']==USED and (journal.state or {})['cleanup_reserve']['cleanup_writes']==USED


def projectable(journal,state):
    return journal.ordinal==34 and identity(state.get(FIELD)) and normal_allowed(journal,state)


def begin_cleanup(journal,state):
    """Atomic first cleanup: use prior durable normal state, never candidate size."""
    old=(journal.state or {}).get(FIELD)
    if old is None:return False
    require(identity(old),'CONTAINED_MARKER')
    new=state.get(FIELD)
    require(new==old,'CONTAINED_MARKER_IMMUTABLE')
    if old['phase']=='NORMAL':
        require(journal.state['cleanup_reserve']['cleanup_writes']==USED,'CONTAINED_CLEANUP_ACCOUNTING')
        state[FIELD]=dict(old,phase='CLEANUP')
        return True
    require(old['phase']=='CLEANUP','CONTAINED_PHASE')
    return False
