"""Option B (specification 033 follow-up, screening-quality note): an ADDITIVE, opt-in screening rule version. Version 1 stays byte-for-byte what it was; version 2 uses the council's CONFIGURED threshold and adds size-assessment fields.
Nothing here re-screens, rewrites or recalculates any stored result. Offline."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.ingestion import listing_screening as ls
from app.ingestion.ledger import digest

# The twenty-four archived Bolton records (RECEIVED 2026-09-28 to 2026-10-04) reduced to what screening reads: reference, proposal, address.
# Source: hosted-sealed-artifact/source/worker-result.json of the 20 October window demonstration (sha256 b3d765e7...). Recorded v1 aggregate: 1 / 3 / 20.
RECORDS=json.loads((Path(__file__).parent/'fixtures'/'bolton_window_24_listing.json').read_text())


def row(r):
    return dict(reference=r['reference'],fields={'proposal':dict(state='PRESENT_VALUE',value=r['proposal'],locator='x',truncated=False),'address':dict(state='PRESENT_VALUE',value=r['address'],locator='x',truncated=False),
                                                 'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})


def synthetic(text,**over):
    return dict(reference='T/1',fields={'proposal':dict(state=over.get('state','PRESENT_VALUE'),value=text,locator='x',truncated=over.get('truncated',False)),'address':dict(state='PRESENT_VALUE',value='1 Test Street',locator='x',truncated=False),
                                        'application_type':dict(state='UNKNOWN',value=None,locator='x',truncated=False)})


def test_version_1_is_the_default_and_is_unchanged_for_all_twenty_four_archived_records():
    v1=[ls.screen_row(row(r)) for r in RECORDS]
    assert all(x['rule_version']=='manchester-listing-screen-assessment-v1' and 'size_assessment' not in x for x in v1)
    from collections import Counter
    assert Counter(x['disposition'] for x in v1)=={'INSUFFICIENT_EVIDENCE':20,'RELATED_APPLICATION_FOLLOW_THROUGH':3,'SUPPORTED_PROCESSING_PRIORITY':1}      # the recorded aggregate
    assert sum(len(x['citations']['occurrences']) for x in v1)==3 and sum(x['proposal_usable'] for x in v1)==24
    assert digest(v1)==digest([ls.screen_row(row(r),rule_version=ls.RULE_V1) for r in RECORDS])
    for bad in (dict(council='bolton'),dict(unit_threshold=10)):
        with pytest.raises(ValueError,match='RULE_V1_TAKES_NO_THRESHOLD'):ls.screen_row(row(RECORDS[0]),**bad)      # v1 cannot be asked for a different behaviour


def test_version_2_is_purely_additive_at_the_default_threshold_for_all_twenty_four():
    for r in RECORDS:
        v1=ls.screen_row(row(r));v2=ls.screen_row(row(r),rule_version=ls.RULE_V2,unit_threshold=10)
        assert {k:v for k,v in v2.items() if k not in ('rule_version','size_assessment','known_unit_count','screening_threshold','size_reason')}=={k:v for k,v in v1.items() if k!='rule_version'}
        assert v2['rule_version']=='manchester-listing-screen-assessment-v2' and v2['screening_threshold']==10 and v2['permanent_exclusion'] is False and v2['retained'] is True


def test_the_six_flat_scheme_is_a_known_size_below_the_threshold_and_nothing_else_in_the_window_changes():
    out={r['reference']:ls.screen_row(row(r),rule_version=ls.RULE_V2,unit_threshold=10) for r in RECORDS}
    six=out['01757/26']
    assert six['disposition']=='INSUFFICIENT_EVIDENCE' and six['size_assessment']=='KNOWN_BELOW_SCREENING_THRESHOLD' and six['known_unit_count']==6 and six['size_reason']=='DWELLING_COUNT_BELOW_THRESHOLD'      # same label as before, now distinguishable
    big=out['01768/26']
    assert big['size_assessment']=='KNOWN_AT_OR_ABOVE_SCREENING_THRESHOLD' and big['known_unit_count']==49 and big['disposition']=='SUPPORTED_PROCESSING_PRIORITY'
    air=out['01797/26']
    assert air['size_assessment']=='SIZE_NOT_ESTABLISHED' and air['known_unit_count'] is None and air['size_reason']=='COUNT_WITHOUT_RESIDENTIAL_WORDING'      # "1 NO. AIR HANDLING UNIT" is not a one-dwelling scheme
    assessed=sorted(k for k,v in out.items() if v['size_assessment']!='SIZE_NOT_ESTABLISHED')
    assert assessed==['01757/26','01768/26']
    assert all(v['known_unit_count'] is None for k,v in out.items() if k not in assessed)


def test_the_threshold_comes_from_the_configuration_not_a_literal():
    pytest.importorskip('yaml')
    assert ls.council_unit_threshold('bolton')==10
    a=ls.screen_row(row(RECORDS[23]),rule_version=ls.RULE_V2,council='bolton');b=ls.screen_row(row(RECORDS[23]),rule_version=ls.RULE_V2,unit_threshold=10)
    assert a==b
    with pytest.raises(KeyError):ls.council_unit_threshold('nowhere')


def test_a_different_configured_threshold_changes_the_assessment_and_the_stated_threshold_only_through_the_existing_qualifier():
    six=synthetic('ERECTION OF TWO STOREY RESIDENTIAL BUILDING COMPRISING 6 SELF CONTAINED FLATS')
    at5=ls.screen_row(six,rule_version=ls.RULE_V2,unit_threshold=5);at10=ls.screen_row(six,rule_version=ls.RULE_V2,unit_threshold=10)
    assert at5['size_assessment']=='KNOWN_AT_OR_ABOVE_SCREENING_THRESHOLD' and at5['screening_threshold']==5 and at10['size_assessment']=='KNOWN_BELOW_SCREENING_THRESHOLD' and at10['screening_threshold']==10
    assert at5['existing_classification'].endswith('5+ units') and at10['existing_classification']=='Ignore - under 10 units'      # the existing qualifier, parameterised by the same number
    for bad in (None,0,-1,'10',10.0):
        with pytest.raises(ValueError):ls.screen_row(six,rule_version=ls.RULE_V2,unit_threshold=bad)
    with pytest.raises(ValueError,match='RULE_V2_REQUIRES_EXACTLY_ONE_OF_COUNCIL_OR_THRESHOLD'):ls.screen_row(six,rule_version=ls.RULE_V2,council='bolton',unit_threshold=10)
    with pytest.raises(ValueError,match='UNKNOWN_SCREENING_RULE_VERSION'):ls.screen_row(six,rule_version='v3')


@pytest.mark.parametrize('text,assessment,reason',[
    ('ERECTION OF 3 RETAIL UNITS',ls.SIZE_NOT_ESTABLISHED,'NOT_RESIDENTIAL_PROPOSAL'),      # the existing qualifier's own non-residential exclusion
    ('SCREENING OPINION FOR 40 DWELLINGS',ls.SIZE_NOT_ESTABLISHED,'ADMINISTRATIVE_OR_SECONDARY_APPLICATION'),
    ('DISCHARGE OF CONDITIONS FOR 20 DWELLINGS',ls.SIZE_NOT_ESTABLISHED,'RELATED_APPLICATION_LEAD'),
    ('CHANGE OF USE OF 12 FLATS TO A HOTEL',ls.SIZE_NOT_ESTABLISHED,'COUNT_DESCRIBES_EXISTING_OR_REMOVED_DWELLINGS'),      # the 12 are the existing flats
    ('DEMOLITION OF 14 EXISTING FLATS',ls.SIZE_NOT_ESTABLISHED,'COUNT_DESCRIBES_EXISTING_OR_REMOVED_DWELLINGS'),
    ('ALTERATIONS TO THE EXISTING 12 FLATS INCLUDING NEW WINDOWS',ls.SIZE_NOT_ESTABLISHED,'COUNT_DESCRIBES_EXISTING_OR_REMOVED_DWELLINGS'),
    ('CONVERSION OF 12 FLATS INTO 24 FLATS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),      # the largest count is the created one
    ('DEMOLITION OF 14 FLATS AND ERECTION OF 12 HOUSES',ls.SIZE_NOT_ESTABLISHED,'COUNT_DESCRIBES_EXISTING_OR_REMOVED_DWELLINGS'),      # the qualifier takes the largest number (14); v2 refuses to call it the scheme size
    ('ERECTION OF A 60 BEDROOM CARE HOME',ls.SIZE_NOT_ESTABLISHED,'COUNT_NOT_ATTACHED_TO_A_DWELLING_NOUN'),      # bedrooms, not dwellings
    ('CHANGE OF USE OF OFFICES TO 12 FLATS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('CONVERSION OF EXISTING BUILDING TO PROVIDE 12 FLATS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('DEMOLITION OF EXISTING BUNGALOW AND ERECTION OF 12 DWELLINGS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('ERECTION OF 12 DWELLINGS FOLLOWING DEMOLITION OF 2 EXISTING HOUSES',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('ERECTION OF TWELVE DWELLINGS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('ERECTION OF 12 NO. 2 STOREY DWELLINGS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('ERECTION OF 12 DWELLINGS WITH ACCESS',ls.SIZE_AT_OR_ABOVE,'DWELLING_COUNT_AT_OR_ABOVE_THRESHOLD'),
    ('ERECTION OF 9 DWELLINGS WITH ACCESS',ls.SIZE_BELOW,'DWELLING_COUNT_BELOW_THRESHOLD'),
    ('ERECTION OF DWELLINGS WITH ACCESS (NUMBER NOT STATED)',ls.SIZE_NOT_ESTABLISHED,'NO_UNIT_COUNT'),
    ('INSTALLATION OF 3 NO. EXTRACT UNITS TO ROOF',ls.SIZE_NOT_ESTABLISHED,'COUNT_WITHOUT_RESIDENTIAL_WORDING'),
    ('NON-MATERIAL AMENDMENT TO APPLICATION 00284/26 TO AMEND 8 DWELLINGS',ls.SIZE_NOT_ESTABLISHED,'RELATED_APPLICATION_LEAD')])
def test_the_size_assessment_states_and_their_fixed_reasons(text,assessment,reason):
    out=ls.screen_row(synthetic(text),rule_version=ls.RULE_V2,unit_threshold=10)
    assert out['size_assessment']==assessment and out['size_reason']==reason
    assert (out['known_unit_count'] is None)==(assessment==ls.SIZE_NOT_ESTABLISHED)


def test_an_unusable_proposal_is_not_assessed_and_stays_insufficient():
    for kw in (dict(state='UNKNOWN'),dict(truncated=True)):
        out=ls.screen_row(synthetic('ERECTION OF 6 FLATS',**kw),rule_version=ls.RULE_V2,unit_threshold=10)
        assert out['disposition']=='INSUFFICIENT_EVIDENCE' and out['size_assessment']=='SIZE_NOT_ESTABLISHED' and out['size_reason']=='PROPOSAL_NOT_USABLE' and out['proposal_usable'] is False


def test_the_function_does_not_mutate_its_input_and_is_deterministic():
    r=row(RECORDS[23]);before=copy.deepcopy(r)
    a=ls.screen_row(r,rule_version=ls.RULE_V2,unit_threshold=10);b=ls.screen_row(r,rule_version=ls.RULE_V2,unit_threshold=10)
    assert a==b and r==before


def test_nothing_in_the_repository_selects_version_2_so_no_existing_screening_changes_and_nothing_re_screens():
    root=Path(__file__).resolve().parents[1];offenders=[]
    for path in list((root/'app').rglob('*.py'))+list((root/'verification').rglob('*.py')):
        if path.name=='listing_screening.py':continue
        text=path.read_text(encoding='utf-8',errors='ignore')
        if 'RULE_V2' in text or "rule_version='manchester-listing-screen-assessment-v2'" in text:offenders.append(str(path.relative_to(root)))
    assert offenders==[]      # opt-in only: no caller selects v2 yet, and there is no re-screening function
    assert not [n for n in dir(ls) if 'rescreen' in n.lower() or 're_screen' in n.lower()]


@pytest.mark.parametrize('text',['CHANGE OF USE OF 12 FLATS TO A HOTEL','DEMOLITION OF 14 EXISTING FLATS','ERECTION OF A 60 BEDROOM CARE HOME','ERECTION OF 3 RETAIL UNITS','DISCHARGE OF CONDITIONS FOR 20 DWELLINGS'])
def test_a_size_that_is_not_established_never_changes_the_disposition_or_any_version_1_field(text):
    v1=ls.screen_row(synthetic(text));v2=ls.screen_row(synthetic(text),rule_version=ls.RULE_V2,unit_threshold=10)
    assert v2['size_assessment']==ls.SIZE_NOT_ESTABLISHED and v2['known_unit_count'] is None
    assert {k:x for k,x in v2.items() if k not in ('rule_version','size_assessment','known_unit_count','screening_threshold','size_reason')}=={k:x for k,x in v1.items() if k!='rule_version'}      # the v1 dispositions (including any v1 weakness) are untouched: v2 only declines to claim a size


def test_the_threshold_is_still_the_configured_ten_and_the_assessment_agrees_with_the_qualifier_for_every_established_size():
    for text in ('ERECTION OF 9 DWELLINGS','ERECTION OF 10 DWELLINGS','ERECTION OF 11 DWELLINGS'):
        q=ls.screen_row(synthetic(text));v2=ls.screen_row(synthetic(text),rule_version=ls.RULE_V2,unit_threshold=10)
        assert (v2['size_assessment']==ls.SIZE_AT_OR_ABOVE)==q['existing_classification'].startswith('Confirmed') and v2['screening_threshold']==10


V1_GOLDEN="bd1585f3f44023771c050807d1906d37ccbaf5b01a6c273ee3167a4f3ba6ffc6"      # digest of master 82988cb listing_screening.screen_row(row) over the inputs below, produced by that unmodified module (this change must not move it)


def test_version_1_output_over_the_archived_records_and_the_probe_wordings_equals_the_digest_recorded_from_master():
    texts=[r["proposal"] for r in RECORDS]+["CHANGE OF USE OF 12 FLATS TO A HOTEL","DEMOLITION OF 14 EXISTING FLATS","ERECTION OF A 60 BEDROOM CARE HOME","ERECTION OF 3 RETAIL UNITS","DISCHARGE OF CONDITIONS FOR 20 DWELLINGS","ERECTION OF TWELVE DWELLINGS","","  "]
    def one(t,**over):
        return dict(reference="T/1",fields={"proposal":dict(state=over.get("state","PRESENT_VALUE"),value=t,locator="x",truncated=over.get("truncated",False)),"address":dict(state="PRESENT_VALUE",value="1 St",locator="x",truncated=False),
                                            "application_type":dict(state="UNKNOWN",value=None,locator="x",truncated=False)})
    assert digest([ls.screen_row(one(t,**kw)) for t in texts for kw in (dict(),dict(state="UNKNOWN"),dict(truncated=True))])==V1_GOLDEN
