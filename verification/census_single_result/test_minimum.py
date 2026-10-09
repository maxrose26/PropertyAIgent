import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture as v1
import minimum as m
from test_capture import SQLAudit
from pglast import parse_sql,ast

def empty(mode='full'):
    _,_,manifest=m.design(mode)
    rows=[dict(record_type=t,row_kind='CONTROL',record_id=None,
        payload=dict(count=0,limit=manifest['bounds'][t],overflow=False)) for t in m.FIELDS]
    rows.append(dict(record_type='__capture',row_kind='CONTROL',record_id=None,payload=dict(
        version=m.VERSION,mode=mode,read_only='on',isolation='repeatable read',
        statement_timeout='5s',lock_timeout='2s',snapshot='1:2:',captured_at='2026-10-09T00:00:00Z',
        backend_pid=123,encoded_upper_bound=1000,row_count=len(rows),overflow=False)))
    return rows

def add(rows,t,values):
    value=dict.fromkeys(m.FIELDS[t].split(','));value.update(values)
    rows.insert(0,dict(record_type=t,row_kind='DATA',record_id=str(value[m.KEYS[t]]),payload=value))
    next(r for r in rows if r['record_type']==t and r['row_kind']=='CONTROL')['payload']['count']+=1
    rows[-1]['payload']['row_count']+=1

class MinimumTests(unittest.TestCase):
    def good(self,r):return m.assemble(r,encoded_bytes=1000,elapsed_seconds=1)
    def rejects(self,mutation):
        rows=empty();mutation(rows)
        with self.assertRaises(ValueError):self.good(rows)
    def test_new_manifest(self):
        self.assertEqual(len(m.FIELDS),11)
        self.assertEqual(self.good(empty())['dependency_census_state'],'QUALIFIED')
    def test_empty_sections_complete(self):self.assertEqual(self.good(empty())['retrieval_state'],'COMPLETE')
    def test_all_minimum_sections(self):
        rows=empty()
        for t in m.FIELDS:
            v={m.KEYS[t]:'oldham' if t=='councils' else 1}
            if 'status' in m.FIELDS[t].split(','):v['status']='active'
            if t=='buyers':v['workspace_id']=1
            if t=='buyer_mandates':v['buyer_id']=1
            add(rows,t,v)
        self.assertEqual(sum(map(len,self.good(rows)['data'].values())),11)
    def test_missing_section(self):self.rejects(lambda r:r.pop(0))
    def test_duplicate_section(self):self.rejects(lambda r:r.append(copy.deepcopy(r[0])))
    def test_count_mismatch(self):self.rejects(lambda r:r[0]['payload'].update(count=2))
    def test_capture_count_mismatch(self):self.rejects(lambda r:r[-1]['payload'].update(row_count=99))
    def test_unknown_schema(self):self.rejects(lambda r:r[-1]['payload'].update(version=v1.VERSION))
    def test_row_overflow(self):self.rejects(lambda r:r[0]['payload'].update(overflow=True))
    def test_byte_overflow(self):self.rejects(lambda r:r[-1]['payload'].update(encoded_upper_bound=10000001))
    def test_runtime_overflow(self):
        with self.assertRaises(ValueError):m.assemble(empty(),encoded_bytes=1000,elapsed_seconds=61)
    def test_unsafe_transaction(self):self.rejects(lambda r:r[-1]['payload'].update(read_only='off'))
    def test_duplicate_key(self):
        r=empty();add(r,'sites',{'id':1});add(r,'sites',{'id':1})
        with self.assertRaises(ValueError):self.good(r)
    def test_removed_section_rejected(self):self.rejects(lambda r:r[0].update(record_type='documents'))
    def test_removed_column_rejected(self):
        r=empty();add(r,'applications',{'id':1});r[0]['payload']['applicant_present']=True
        with self.assertRaises(ValueError):self.good(r)
    def test_cross_scope_is_explicit(self):
        r=empty();add(r,'local_plan_sites',{'id':1,'matched_site_id':999})
        self.assertEqual(self.good(r)['unresolved'][0]['qualification'],'UNRESOLVED_OUTSIDE_CAPTURE_SCOPE')
    def test_buyer_fk_fails(self):
        r=empty();add(r,'buyer_mandates',{'id':1,'buyer_id':99,'status':'active'})
        with self.assertRaises(ValueError):self.good(r)
    def test_no_membership_invention(self):
        result=self.good(empty())
        self.assertNotIn('buyer_subject_membership',result)
        self.assertNotIn('risk_cohorts',result)
    def test_types_still_distinct(self):
        kinds=['DIRECT_FACTUAL_DEPENDENCY','CONTEXT_DEPENDENCY','DISCOVERY_RELATIONSHIP']
        result=v1.preserve_dependencies([dict(dependency_type=k) for k in kinds])
        self.assertEqual(set(result),set(kinds))
    def test_canary_replaces_only_phase_site(self):
        self.assertEqual(m.COHORT,(25,28,254,58,179,281))
        _,_,manifest=m.design('canary')
        self.assertEqual(manifest['bounds']['applications'],100)
        self.assertEqual(len(manifest['sections']),11)
    def test_sql_parse_safety(self):
        for mode in ('canary','full'):
            sql,wrapper,manifest=m.design(mode);parsed=parse_sql(sql)
            self.assertEqual(len(parsed),1);self.assertIsInstance(parsed[0].stmt,ast.SelectStmt)
            audit=SQLAudit();audit(parsed)
            self.assertEqual(audit.tables,{('public',t) for t in m.FIELDS})
            self.assertTrue(audit.functions<={'min','coalesce','count','sum','octet_length','row_to_json','to_jsonb','jsonb_build_object','current_setting','pg_current_snapshot','statement_timestamp','pg_backend_pid'})
            self.assertEqual(len(parse_sql(wrapper)),6)
            for token in ('extracted_text','source_excerpt','regexp_','jsonb_agg','OFFSET','RECURSIVE','headline','overview','applicant_name_raw','title_number'):
                self.assertNotIn(token,sql)
    def test_v1_query_identity_preserved(self):
        _,wrapper,_=v1.design('canary')
        self.assertEqual(hashlib.sha256(wrapper.encode()).hexdigest(),'53fcd27b246f8ca2a0e7f3ed2941ff4490eecf8c63a24ebae0932bd2f9e9321a')
    def test_deterministic_generation(self):self.assertEqual(m.design(),m.design())
    def test_field_classification_complete(self):
        f=json.loads((Path(__file__).parent/'field-necessity.json').read_text())
        expected={t+'.'+c for t,cols in v1.FIELDS.items() for c in cols.split(',')}
        self.assertTrue(expected<=set(f))
        retained={k for k,v in f.items() if v['retained']}
        self.assertEqual(retained,{t+'.'+c for t,cols in m.FIELDS.items() for c in cols.split(',')})
    def test_parent_case_has_separate_evidenced_records(self):
        f=json.loads((Path(__file__).parent/'coverage-fixture.json').read_text())['pair']
        self.assertEqual(f['child']['id'],284);self.assertEqual(f['parent']['id'],566)
        self.assertNotEqual(f['child']['reference'],f['parent']['reference'])
        self.assertIn(f['parent']['reference'],f['evidence']['council_retained_observation']['table'])
        self.assertIsNone(f['parent']['status_verified_at'])
        self.assertIsNotNone(f['child']['status_verified_at'])

    def test_existing_parser_and_freshness_adapter(self):
        repo=Path(__file__).resolve().parents[1]/'PropertyAIgent-l0-final'
        if not repo.exists():
            repo=Path(__file__).resolve().parents[2]
        sys.path.insert(0,str(repo))
        from app.reporting.subject_relationships import scan_parent_citations
        from app.reporting.planning_freshness import present_planning_freshness
        f=json.loads((Path(__file__).parent/'coverage-fixture.json').read_text())['pair']
        scan=scan_parent_citations(f['child']['proposal'])
        self.assertEqual([x.reference for x in scan.qualifying],[f['parent']['reference']])
        self.assertEqual(f['child']['council_code'],f['parent']['council_code'])
        now=dt.datetime(2026,10,9,tzinfo=dt.timezone.utc)
        def position(record):
            r=types.SimpleNamespace(**record,summary_url=None)
            r.status_verified_at=dt.datetime.fromisoformat(record['status_verified_at']) if record['status_verified_at'] else None
            return present_planning_freshness(r,now=now)
        child=position(f['child']);parent=position(f['parent'])
        self.assertIsNone(parent.last_successful_verification)
        self.assertEqual(parent.freshness,'verification_unavailable')
        self.assertEqual(child.last_successful_verification,dt.datetime.fromisoformat(f['child']['status_verified_at']))
        # Reverse the observations synthetically: parent verification still cannot certify child.
        reversed_parent=dict(f['parent'],status_verified_at=f['child']['status_verified_at'])
        reversed_child=dict(f['child'],status_verified_at=None)
        self.assertIsNone(position(reversed_child).last_successful_verification)
        self.assertIsNotNone(position(reversed_parent).last_successful_verification)

    def coverage_input(self):
        f=json.loads((Path(__file__).parent/'coverage-fixture.json').read_text())['pair']
        apps=[dict(id=i,site_id=s,reference=r) for s,i,r in [
            (25,29,'FUL/355201/25'),(28,42,'FUL/355686/26'),(254,305,'117614/FUL/25'),
            (58,78,'DC/078942'),(281,358,'VAR/349651/22'),(281,737,'OUT/345898/20')]]
        apps.extend([copy.deepcopy(f['child']),copy.deepcopy(f['parent'])])
        return dict(retrieval_state='COMPLETE',dependency_census_state='QUALIFIED',
            data=dict(sites=[dict(id=i) for i in m.COHORT],applications=apps))

    def test_coverage_pair_accepts_exact_records(self):
        self.test_existing_parser_and_freshness_adapter()
        from acceptance import check_canary_coverage
        result=check_canary_coverage(self.coverage_input())
        self.assertEqual(result['acquisition_containment'],'NOT_ESTABLISHED')
        self.assertIsNone(result['parent_verified_at'])
    def test_coverage_missing_parent_fails(self):
        self.test_existing_parser_and_freshness_adapter()
        from acceptance import check_canary_coverage
        r=self.coverage_input();r['data']['applications'].pop()
        with self.assertRaises(ValueError):check_canary_coverage(r)
    def test_coverage_incidental_phase_words_fail(self):
        self.test_existing_parser_and_freshness_adapter()
        from acceptance import check_canary_coverage
        r=self.coverage_input();r['data']['applications'][-2]['proposal']='Phase 2 housing near an earlier scheme'
        with self.assertRaises(ValueError):check_canary_coverage(r)
    def test_coverage_wrong_council_fails(self):
        self.test_existing_parser_and_freshness_adapter()
        from acceptance import check_canary_coverage
        r=self.coverage_input();r['data']['applications'][-1]['council_code']='wigan'
        with self.assertRaises(ValueError):check_canary_coverage(r)

if __name__=='__main__':unittest.main()
