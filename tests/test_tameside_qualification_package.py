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
