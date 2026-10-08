"""Versioned dependency integrity: corruption must fail, not merely happy-path pins."""
import ast
import json
from pathlib import Path
import shutil
import pytest
from tests.stage26b_integrity import assert_historical_and_successor,MANIFEST,digest,definitions

ROOT=Path(__file__).resolve().parents[1]
HISTORICAL='9eaafa1d502acc12be56a19a4b0d701c9ada132f778a842df547905eb5af62d1'


def test_historical_and_current_successor_integrity():
    assert_historical_and_successor(ROOT,HISTORICAL)


@pytest.mark.parametrize('surface',['historical','manifest','eligibility','approved','proposed','portal','legacy','constant','binding','position','decorator','predecessor','creation','ancillary'])
def test_corrupted_contract_or_runtime_dependency_fails(tmp_path,surface):
    contract=json.loads((ROOT/MANIFEST).read_text())
    files={MANIFEST,contract['predecessor']['fixture'],contract['historical']['fixture'],*contract['definition_pins'],*contract['module_pins']}
    for name in files:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    choices={
      'predecessor':(contract['predecessor']['fixture'],'stage26b-b1-reconciliation-v1','stage26b-b1-reconciliation-v2'),
      'creation':('app/reporting/residential_count_eligibility.py','creation_matches = list(re.finditer(building_creation, text))','creation_matches = []'),
      'ancillary':('app/reporting/residential_count_eligibility.py','if ancillary_action:', 'if False:'),
      'historical':(contract['historical']['fixture'],'FACT_RESOLVED = "resolved"','FACT_RESOLVED = "changed"'),
      'manifest':(MANIFEST,'stage26b-b11-reconciliation-v1','stage26b-b11-reconciliation-v2'),
      'eligibility':('app/reporting/residential_count_eligibility.py','return CountEligibility("existing_stock_works")','return CountEligibility()'),
      'approved':('app/reporting/scheme_reconciliation.py','def _resolve_approved_units','def _changed_approved_units'),
      'proposed':('app/reporting/scheme_reconciliation.py','def _build_active_position','def _changed_active_position'),
      'portal':('app/reporting/scheme_reconciliation.py','def _portal_estimated_units','def _changed_portal_estimated_units'),
      'legacy':('app/reporting/entity_search.py','units = eligible_residential_scalar(app, units)','units = units'),
      'decorator':('app/reporting/scheme_reconciliation.py','def _resolve_approved_units','@staticmethod\ndef _resolve_approved_units'),
      'binding':('app/reporting/scheme_reconciliation.py','FACT_RESOLVED = "resolved"','FACT_RESOLVED = "resolved"; _resolve_approved_units = None'),
      'position':('app/reporting/scheme_reconciliation.py','def _position','def _changed_position'),
      'constant':('app/reporting/scheme_reconciliation.py','FACT_RESOLVED = "resolved"','FACT_RESOLVED = "changed"')}
    name,old,new=choices[surface];p=tmp_path/name;text=p.read_text();assert old in text;p.write_text(text+'\n_resolve_approved_units = None\n' if surface=='binding' else text.replace(old,new,1))
    with pytest.raises(AssertionError):assert_historical_and_successor(tmp_path,HISTORICAL)


def test_qualified_oracles_never_call_raw_reconciliation(monkeypatch):
    import app.reporting.scheme_reconciliation as reconciliation
    import app.policy.buyer_matching as current
    from app.policy.buyer_profiles import BUYER_PROFILES
    from verification.transition import frozen_v6_matcher,frozen_v7_matcher
    from app.reporting.residential_count import CountAssessment
    def forbidden(*args,**kwargs):raise AssertionError('Raw reconciliation called for already-qualified input')
    contract=json.loads((ROOT/MANIFEST).read_text())
    for name in contract['definition_pins']['app/reporting/scheme_reconciliation.py']:
        monkeypatch.setattr(reconciliation,name,forbidden)
    for precision,value,lo,hi in [('EXACT',100,100,100),('APPROXIMATE',100,100,102),('RANGE',None,90,110),('UNKNOWN',None,None,None)]:
        count=CountAssessment('site','Site','site:1',precision=precision,value=value,lower=lo,upper=hi)
        facts=current.MatchingFacts('planning_delivery',value,'houses',False,30,True,30,'permission_granted',True,True,False,count_assessment=count)
        for buyer in BUYER_PROFILES.values():
            for oracle in (frozen_v6_matcher.assess_buyer_fit,frozen_v7_matcher.assess_buyer_fit,current.assess_buyer_fit):
                assert oracle(buyer,facts,current.B2MatchingContext(council_code='stockport')).classification
