import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture import assemble, design, FIELDS, KEYS, LIMITS, VERSION, preserve_dependencies
from pglast import parse_sql, ast
from pglast.visitors import Visitor

def fixture():
    rows=[]
    for t in FIELDS:
        rows.append(dict(record_type=t,row_kind='CONTROL',record_id=None,payload=dict(count=0,limit=LIMITS[t],overflow=False)))
    rows.append(dict(record_type='__capture',row_kind='CONTROL',record_id=None,payload=dict(version=VERSION,mode='full',read_only='on',isolation='repeatable read',statement_timeout='5s',lock_timeout='2s',snapshot='1:2:',captured_at='2026-10-09T00:00:00Z',backend_pid=123,logical_bytes=1000,encoded_upper_bound=6096,row_count=len(rows),overflow=False)))
    return rows

def add(rows,t,values):
    allowed=set(FIELDS[t].split(','))|({'applicant_present'} if t=='applications' else {'title_present'} if t=='control_relationships' else {'headline_present','overview_present'} if t=='allocation_intelligence_summaries' else set())
    value=dict.fromkeys(allowed);value.update(values)
    rows.insert(0,dict(record_type=t,row_kind='DATA',record_id=str(value[KEYS[t]]),payload=value))
    next(r for r in rows if r['record_type']==t and r['row_kind']=='CONTROL')['payload']['count']+=1
    rows[-1]['payload']['row_count']+=1

class SQLAudit(Visitor):
    def __init__(self): super().__init__();self.functions=set();self.tables=set()
    def visit_FuncCall(self,ancestors,node): self.functions.add('.'.join(n.sval for n in node.funcname))
    def visit_RangeVar(self,ancestors,node):
        if node.schemaname:self.tables.add((node.schemaname,node.relname))
    def visit_InsertStmt(self,*a):raise AssertionError('DML')
    def visit_UpdateStmt(self,*a):raise AssertionError('DML')
    def visit_DeleteStmt(self,*a):raise AssertionError('DML')
    def visit_A_Star(self,*a):raise AssertionError('Unrestricted star')

class CaptureTests(unittest.TestCase):
    def good(self,r): return assemble(r,encoded_bytes=1000,elapsed_seconds=1)
    def rejects(self,mutate):
        r=fixture();mutate(r)
        with self.assertRaises(ValueError):self.good(r)
    def test_complete_empty_sections(self):self.assertEqual(self.good(fixture())['retrieval_state'],'COMPLETE')
    def test_all_sections_reconstruct(self):
        r=fixture()
        for t in FIELDS:
            values={KEYS[t]:'oldham' if t=='councils' else 1}
            if 'status' in FIELDS[t].split(','):values['status']='active'
            if t=='buyers':values['workspace_id']=1
            if t=='buyer_mandates':values['buyer_id']=1
            add(r,t,values)
        self.assertEqual(sum(map(len,self.good(r)['data'].values())),16)
    def test_missing_section(self):self.rejects(lambda r:r.pop(0))
    def test_duplicate_control(self):self.rejects(lambda r:r.append(copy.deepcopy(r[0])))
    def test_total_count_mismatch(self):self.rejects(lambda r:r[-1]['payload'].update(row_count=99))
    def test_section_count_mismatch(self):self.rejects(lambda r:r[0]['payload'].update(count=1))
    def test_overflow(self):self.rejects(lambda r:r[0]['payload'].update(overflow=True))
    def test_unknown_version(self):self.rejects(lambda r:r[-1]['payload'].update(version='unknown'))
    def test_unknown_section(self):self.rejects(lambda r:r[0].update(record_type='users'))
    def test_unsafe_transaction(self):self.rejects(lambda r:r[-1]['payload'].update(read_only='off'))
    def test_missing_snapshot(self):self.rejects(lambda r:r[-1]['payload'].update(snapshot=None))
    def test_wrong_timeout(self):self.rejects(lambda r:r[-1]['payload'].update(statement_timeout='60s'))
    def test_byte_ceiling(self):
        with self.assertRaises(ValueError):assemble(fixture(),encoded_bytes=10000001,elapsed_seconds=1)
    def test_runtime_ceiling(self):
        with self.assertRaises(ValueError):assemble(fixture(),encoded_bytes=1000,elapsed_seconds=61)
    def test_duplicate_data(self):
        r=fixture();add(r,'sites',{'id':1});add(r,'sites',{'id':1})
        with self.assertRaises(ValueError):self.good(r)
    def test_unresolved_context_explicit(self):
        r=fixture();add(r,'applications',{'id':42,'site_id':28,'reference':'FUL/355686/26','status':'Awaiting decision'})
        self.assertEqual(self.good(r)['unresolved'][0]['qualification'],'UNRESOLVED_OUTSIDE_CAPTURE_SCOPE')
    def test_unresolved_buyer_fails(self):
        r=fixture();add(r,'buyers',{'id':1,'workspace_id':1,'status':'active'})
        with self.assertRaises(ValueError):self.good(r)
    def test_cross_workspace_fails(self):
        r=fixture();add(r,'workspaces',{'id':2});add(r,'buyers',{'id':1,'workspace_id':2,'status':'active'})
        with self.assertRaises(ValueError):self.good(r)
    def test_private_column_rejected(self):
        r=fixture();add(r,'applications',{'id':42});r[0]['payload']['applicant_name_raw']='secret'
        with self.assertRaises(ValueError):self.good(r)
    def test_dependency_types_preserved(self):
        kinds=['DIRECT_FACTUAL_DEPENDENCY','CONTEXT_DEPENDENCY','DISCOVERY_RELATIONSHIP']
        result=preserve_dependencies([dict(dependency_type=k,application_id=42) for k in kinds])
        self.assertEqual([len(result[k]) for k in kinds],[1,1,1])
    def test_dependency_unknown_rejected(self):
        with self.assertRaises(ValueError):preserve_dependencies([dict(dependency_type='RELATED')])
    def test_retrieval_does_not_certify_census(self):self.assertEqual(self.good(fixture())['dependency_census_state'],'QUALIFIED')
    def test_server_side_guard_is_present(self):
        sql,_,_=design()
        self.assertIn("FROM rows WHERE (SELECT encoded_upper_bound<=10000000 FROM budget)",sql)
        self.assertIn("6*coalesce(sum(octet_length(row_to_json(r)::text)+2),0)+4096",sql)
    def test_conservative_transport_bound(self):
        import csv,io,json
        for text in ['a'*1000,'"\\'*1000,'\u2603'*1000,'\U0001f600'*1000,'\n\t'*1000]:
            row=dict(record_type='applications',row_kind='DATA',record_id='42',payload={'proposal':text})
            base=len(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode())+2
            wire=len(json.dumps([row],ensure_ascii=True).encode())
            out=io.StringIO();csv.writer(out).writerow([row['record_type'],row['row_kind'],row['record_id'],json.dumps(row['payload'],ensure_ascii=True)])
            self.assertLessEqual(max(wire,len(out.getvalue().encode())),6*base+4096)
    def test_ui_truncation_fails(self):
        r=fixture();add(r,'sites',{'id':1});r.pop(0)
        with self.assertRaises(ValueError):self.good(r)
    def test_one_select_static_full_and_canary(self):
        for mode in ('full','canary'):
            sql,wrapper,manifest=design(mode);tree=parse_sql(sql)
            self.assertEqual(len(tree),1);self.assertIsInstance(tree[0].stmt,ast.SelectStmt)
            visitor=SQLAudit();visitor(tree)
            self.assertTrue(visitor.functions <= {'coalesce','min','count','sum','octet_length','to_jsonb','jsonb_build_object','current_setting','pg_current_snapshot','statement_timestamp','pg_backend_pid','row_to_json'})
            self.assertTrue(visitor.tables <= {('public',t) for t in FIELDS})
            self.assertEqual(len(parse_sql(wrapper)),6)
            self.assertNotIn('extracted_text',sql);self.assertNotIn('regexp_',sql);self.assertNotIn('sha256',sql);self.assertNotIn('jsonb_agg',sql)
            self.assertNotIn('RECURSIVE',sql);self.assertNotIn('OFFSET',sql)
            self.assertEqual(len(manifest['sections']),16)

if __name__=='__main__':unittest.main()
