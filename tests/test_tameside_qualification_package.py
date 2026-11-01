"""Only the new one-scope launcher; supervised source is synthetic, never live."""
import json
from datetime import date
from pathlib import Path

import pytest
from tests.e2e_connection_support import idox_audit, entry, SCHEME
from verification.discovery import tameside_qualification as q


def supervisor(*args,**kw):
    assert kw['source'] is True and kw['seconds']==45 and kw['environment']=={'INGESTION_SOURCE_PRIVATE':'ONCE'}
    command=args[0];plan=json.loads(Path(command[command.index('--plan')+1]).read_bytes())
    assert plan==dict(row=q.ROW,fixture=None)
    raw=idox_audit('tameside',[entry('SYNTHETIC/26',SCHEME)],date(2026,10,24),date(2026,10,30))
    Path(command[command.index('--output')+1]).write_text(json.dumps(raw))
    Path(kw['root']).mkdir()
    return dict(cleanup='CLOSED',exit_code=0,limit_hit=None,elapsed_seconds=.1,peak_owned_rss=1024,
                live_owned_survivors=0,expired=False,accounting_complete=True)


def test_fixed_scope_existing_supervisor_and_complete_projection(tmp_path):
    result=q.qualify(tmp_path/'once',supervisor=supervisor)
    assert result['record_count']==1 and result['database_connections']==0 and result['persistence'] is False
    assert result['row']==q.ROW and result['limits']['requests']==10 and result['limits']['source_export_bytes']==524288
    with pytest.raises(q.Denied):q.qualify(tmp_path/'once',supervisor=supervisor)


def test_uncertain_source_closure_preserves_consumption_and_refuses(tmp_path):
    def uncertain(*args,**kw):
        result=supervisor(*args,**kw);result['cleanup']='UNCERTAIN';return result
    path=tmp_path/'uncertain'
    with pytest.raises(q.Denied):q.qualify(path,supervisor=uncertain)
    assert (path/'CONSUMED').is_file() and (path/'source.json').is_file() and (path/'outer.json').is_file()


def test_different_council_is_not_relabelled_to_obtain_qualification(tmp_path):
    def wrong(*args,**kw):
        result=supervisor(*args,**kw);command=args[0];p=Path(command[command.index('--output')+1])
        source=json.loads(p.read_bytes());source['council']='bolton';p.write_text(json.dumps(source));return result
    with pytest.raises(q.Denied):q.qualify(tmp_path/'wrong',supervisor=wrong)


def test_cli_single_use_record_prevents_new_output_path_from_becoming_new_authority(tmp_path,monkeypatch):
    import os,sys
    for key in list(os.environ):
        if 'DATABASE' in key or key.endswith(('_KEY','_TOKEN','_PASSWORD')):monkeypatch.delenv(key)
    monkeypatch.setattr(q,'CONSUMPTION',tmp_path/'consumed.json');calls=[]
    def synthetic(path):
        calls.append(path)
        return dict(status='SYNTHETIC_TEST_ONLY',record_count=0,pages=1,source_sha256='1'*64)
    monkeypatch.setattr(q,'qualify',synthetic)
    monkeypatch.setattr(sys,'argv',['qualification','--output',str(tmp_path/'first'),'--authority',q.AUTHORITY])
    assert q.main()==0
    monkeypatch.setattr(sys,'argv',['qualification','--output',str(tmp_path/'replacement'),'--authority',q.AUTHORITY])
    with pytest.raises(SystemExit,match='CONSUMED'):q.main()
    assert len(calls)==1 and q.CONSUMPTION.stat().st_mode&0o777==0o600
