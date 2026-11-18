"""Reuse stopped deployment with distinct correction intents, never replay originals."""
import ast,copy,hashlib,inspect,time
from . import tameside_preparation as preparation

NAMES=('BUILD_ENVIRONMENT','BUILD_CONFIGURATION','ONE_RESUME_BUILD','RESUSPEND',
       'RESTORE_BUILD_CONFIGURATION','RESTORE_BUILD_ENVIRONMENT')

def prior_deploy_reference(state,pinned):
    """Exact old deploy membership is immutable in retained STOP15 row18.

    Store a digest-checked location, not a second copy of its full ID list.
    The currently observed deployment inventory remains in original_deploy_ids
    for the frozen stopped-deployment overlap and restoration guards.
    """
    from . import tameside_stop15 as plan
    original=state['elapsed_package']
    preparation.require(original['ordinal']==18 and original['sha256']==plan.CHECKPOINT,
                        'STOP15_OLD_DEPLOYMENT_ARCHIVE')
    ids=state['original_deploy_ids']
    preparation.require(isinstance(ids,list) and all(isinstance(x,str) for x in ids),
                        'STOP15_OLD_DEPLOYMENT_IDENTITIES')
    return dict(ordinal=18,checkpoint_sha256=plan.CHECKPOINT,
                count=len(ids),members_sha256=hashlib.sha256(pinned.canonical(ids)).hexdigest())


def operation(runner):
    state=copy.deepcopy(runner.state)
    p=preparation.StoppedDeployment.__new__(preparation.StoppedDeployment)
    p.pinned=runner.pinned;p.db=runner.db;p.api_factory=runner.api_factory
    p.revision=runner.plan_runtime if hasattr(runner,'plan_runtime') else __import__(runner.__module__,fromlist=['plan']).plan.RUNTIME
    p.clock=time.time;p.interrupt=lambda _:None
    p.provider_calls=0;p.provider_bytes=0;p.provider_started=time.monotonic()
    p.journal=runner.journal;p.state=state
    # Keep the same scoped codec during independent reopen/readback. The
    # generic pre-upgrade deployment path must retain its original 32KiB reader.
    def save(self):
        from .tameside_stop15 import read_journal
        if self.state.get('status')=='STOPPED_BUILD_READY':
            self.state['binding']['retained_deployment']=self.state['deployment']
        wanted=copy.deepcopy(self.state)
        try:self.journal.save(wanted)
        except Exception:
            preparation.require(read_journal(self.journal)==wanted,'PREPARATION_CHECKPOINT_ACK_UNKNOWN')
        preparation.require(read_journal(self.journal)==wanted,'PREPARATION_CHECKPOINT_READBACK')
        self.state=wanted
    p.save=save.__get__(p,type(p))
    runner.phase();p.call=runner.api
    # Use the original restore baseline, but compare new deployments against
    # the independently observed pre-correction inventory. The old list is
    # immutable in original checkpoint/row18 and also retained here.
    if 'replacement_deployment' not in state:
        current,_,_,deps=runner.provider()
        # Frozen guard preserves provider field order. Build its expected
        # projection from the fresh response, not canonically stored JSON.
        configured=copy.deepcopy(current)
        configured['branch']='pa-tam002/'+p.revision
        configured['serviceDetails']['envSpecificDetails'].update(buildCommand=preparation.BUILD_COMMAND,startCommand='/bin/true')
        state['replacement_deployment']=dict(prior_revision=state['source_revision'],prior_deployment=state['deployment'],prior_deploy_ids_ref=prior_deploy_reference(state,runner.pinned),revision=p.revision)
        state['original_deploy_ids']=[x['id'] for x in deps]
        state['build_guard']=runner.pinned.service_guard(configured)
        p.save()
    preparation.require(state['replacement_deployment']['revision']==p.revision,'STOP15_REPLACEMENT_PIN')
    # Exact existing methods, with only effect names prefixed. Source is bound
    # in the owner package; no change to sequencing/guards/ack reconciliation.
    scope=dict(vars(preparation))
    for name in ('prepare','restore'):
        code=inspect.getsource(getattr(preparation.StoppedDeployment,name))
        import textwrap
        code=textwrap.dedent(code)
        for original in NAMES:code=code.replace("'"+original+"'","'STOP15_REPLACEMENT_"+original+"'")
        exec(compile(code,preparation.__file__+'[STOP15-replacement]','exec'),scope)
        setattr(p,name,scope[name].__get__(p,type(p)))
    return p
