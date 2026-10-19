"""The evidence-branch primitives the two controllers rely on, exercised with the REAL gh binary against the loopback fixture (no database): README.md anchor present, an unpublished file answers a confirmed
404 (absent), a published file is present with its git blob identity, trees are cumulative (an earlier file remains at a later head), and a non-404 failure is Uncertain."""
import json,shutil,subprocess
import pytest
from verification.ingestion_storage.operational_publication import GitHub,Uncertain,blob_bytes
from tests.storage_gh_fixture import real_gh_store

DIRECTORY='docs/design/ingestion-operational-execution-fixture/capture'
CONTENTS='repos/maxrose26/PropertyAIgent/contents/'


@pytest.mark.skipif(shutil.which('gh') is None,reason='Linux gh required')
@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_probe_publish_and_cumulative_trees_with_the_real_gh_against_the_loopback_fixture(real_gh_store):
    metadata,_,_,requests=real_gh_store
    def runner(command,**kwargs):
        if command[1:4]==['api','--method','GET']:kwargs['allow_failure']=True
        return metadata.cli(command,**kwargs)
    gh=GitHub(lambda *a:None,lambda:None,runner=runner,bound=60)
    head0='1'*40
    anchor=gh.probe(CONTENTS+'README.md?ref='+head0)
    assert anchor is not None and blob_bytes(anchor)==b'disposable evidence branch anchor\n'
    assert gh.probe(CONTENTS+DIRECTORY+'/source.json?ref='+head0) is None      # a confirmed 404: not published yet
    head1=gh.publish({'source.json':b'{"raw":1}'},directory=DIRECTORY,expected_head=head0)
    assert blob_bytes(gh.probe(CONTENTS+DIRECTORY+'/source.json?ref='+head1))==b'{"raw":1}'
    assert gh.probe(CONTENTS+'README.md?ref='+head1) is not None      # the anchor survives a publication (cumulative tree)
    head2=gh.publish({'retained.json':b'{"m":1}'},directory=DIRECTORY.replace('capture','capture-retained'),expected_head=head1)
    assert blob_bytes(gh.probe(CONTENTS+DIRECTORY+'/source.json?ref='+head2))==b'{"raw":1}'      # an EARLIER file is still present at a LATER head: a poll that sees only head2 still finds it
    assert blob_bytes(gh.probe(CONTENTS+DIRECTORY.replace('capture','capture-retained')+'/retained.json?ref='+head2))==b'{"m":1}'
    assert gh.probe(CONTENTS+DIRECTORY+'/source.json?ref='+head0) is None      # ...and the older head still does not contain it
    assert gh.probe(CONTENTS+DIRECTORY.replace('capture','completed')+'/final-result.json?ref='+head2) is None
    assert gh.probe('repos/maxrose26/PropertyAIgent/not-a-route') is None      # a wrong route also answers 404: absence is meaningful ONLY together with the README.md anchor read at the same head (both controllers require it)
    with pytest.raises(Uncertain):gh.publish({'x.json':b'{}'},directory=DIRECTORY,expected_head=head0)      # a stale expected head is refused (EVIDENCE_HEAD_MOVED_RECONCILE)


@pytest.mark.skipif(shutil.which('gh') is None,reason='Linux gh required')
@pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
def test_the_owner_freshness_and_wait_methods_work_end_to_end_with_the_real_gh_and_the_fixture(real_gh_store):
    """The owner's own methods (not just the primitives) against the real gh: freshness passes on a clean branch, a leftover file fails it, and the wait finds a file published several commits ago."""
    from verification.ingestion_storage import operational_runner as orr
    from verification.ingestion_storage import stable_pipeline as sp
    metadata,_,_,_=real_gh_store
    def runner(command,**kwargs):
        if command[1:4]==['api','--method','GET']:kwargs['allow_failure']=True
        return metadata.cli(command,**kwargs)
    gh=GitHub(lambda *a:None,lambda:None,runner=runner,bound=80)
    owner=object.__new__(orr.Runner)
    owner.github=gh;owner.r=dict(evidence_directory=sp.EVIDENCE_DIRECTORY);owner.check=lambda:None;owner.stop_requested=lambda:None;owner.pipeline_sleep=lambda s:None;owner.evidence_head='1'*40
    owner.require_fresh_evidence_directory()      # a clean branch: the anchor is readable and none of the three files exists
    head1=gh.publish({'source.json':b'{"raw":1}'},directory=sp.EVIDENCE_DIRECTORY+'/capture',expected_head='1'*40)
    head2=gh.publish({'retained.json':b'{"m":1}'},directory=sp.EVIDENCE_DIRECTORY+'/capture-retained',expected_head=head1)
    head3=gh.publish({'other.json':b'{}'},directory=sp.EVIDENCE_DIRECTORY+'/screening-authority',expected_head=head2)      # later commits keep arriving
    head,relative,blob=owner.await_any(('capture-retained/retained.json','completed/final-result.json'),5)
    assert head==head3 and relative=='capture-retained/retained.json' and blob_bytes(blob)==b'{"m":1}'      # found at the CURRENT head although it was published two commits earlier
    owner.evidence_head=head3
    with pytest.raises(Uncertain,match='EVIDENCE_DIRECTORY_NOT_FRESH'):owner.require_fresh_evidence_directory()      # a leftover from an earlier run is refused
