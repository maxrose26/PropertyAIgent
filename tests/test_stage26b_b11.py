"""Retained production proposals plus held-out scope/action regression controls.

Proposal truth is date-bound retained production evidence from 8 October 2026;
these fixtures do not assert current council verification or ownership facts.
"""
import pytest
from app.db.models import Application, SchemeIntelligence
from app.reporting.residential_count_eligibility import residential_count_eligibility, eligible_residential_scalar
from app.reporting.scheme_reconciliation import build_operative_planning_facts, count_assessment_for_facts

RENOLD = ('Erection of a 5 storey mixed-use development with retail (Use Class E) at the ground floor '
          'with 56 apartments (Class C3) and associated roof terrace above, together with car parking '
          'facilities, landscaping, and associated infrastructure following demolition of existing buildings.')
WOODFORD = ('Application for reserved matters approval for landscaping works adjoining infrastructure '
            'phase H4 of hybrid application ref. DC/053832')

@pytest.mark.parametrize('pending',[True,False])
@pytest.mark.parametrize('proposal,raw,expected',[(RENOLD,56,56),(WOODFORD,372,None)])
def test_retained_production_evidence_in_approved_and_proposed_paths(pending,proposal,raw,expected):
    app=Application(id=1,site_id=1,reference='SYNTHETIC',proposal=proposal,
                    status='Awaiting decision' if pending else 'Decided',
                    decision=None if pending else 'Granted',
                    decision_issued_date=None if pending else '2026-01-01',
                    application_received='2025-01-01',estimated_unit_count=raw)
    app.scheme_intelligence=SchemeIntelligence(total_units_final=raw)
    count=count_assessment_for_facts(build_operative_planning_facts([app]))
    assert count.exact_value==expected
    assert eligible_residential_scalar(app,raw)==expected
    assert app.scheme_intelligence.total_units_final==raw
    if expected is None: assert count.precision=='UNKNOWN'

@pytest.mark.parametrize('proposal,count',[
 ('Construction of a six-storey building comprising 80 apartments following demolition of existing buildings',80),
 ('Erection of a new three-storey residential building with 56 apartments and roof terrace following demolition of existing buildings',56),
 ('Erection of a residential block containing 45 flats with roof terraces and landscaping',45),
 ('Erection of 100 homes with demolition, bridges, infrastructure and landscaping',100),
 ('Reserved matters approval for landscaping and erection of 72 dwellings',72),
 ('Reserved matters approval for landscaping adjoining a public park and erection of 72 dwellings',72),
 ('Conversion of existing commercial building into 24 apartments with roof terrace',24),
 ('Change of use of existing offices to 30 homes including landscaping',30),
])
def test_explicit_residential_creation_survives_incidental_works(proposal,count):
    assert residential_count_eligibility(Application(proposal=proposal),count).eligible

@pytest.mark.parametrize('proposal,count',[
 (WOODFORD+' for parent scheme of 372 homes',372),
 ('Construction of a replacement roof to a residential building with 56 existing apartments',56),
 ('Erection of a roof terrace above an existing building containing 56 flats',56),
 ('Reserved matters approval for landscaping works adjacent to erection of 372 dwellings in the parent scheme',372),
 ('Landscaping works pursuant to erection of 372 dwellings',372),
 ('Reserved matters approval for landscaping works associated with erection of 372 dwellings',372),
 ('Reserved matters approval for landscaping in connection with erection of 372 dwellings',372),
 ('Reserved matters approval for infrastructure works pursuant to erection of 372 dwellings',372),
 ('Reserved matters for landscaping works of hybrid application for erection of 372 dwellings',372),
 ('Construction of landscaping works adjoining development of 372 homes',372),
 ('Erection of replacement porches to 56 existing homes with roof repairs',56),
])
def test_ancillary_action_cannot_borrow_parent_or_existing_stock_quantum(proposal,count):
    assert not residential_count_eligibility(Application(proposal=proposal),count).eligible


def test_building_creation_still_rejects_conflicting_scalar():
    assert not residential_count_eligibility(Application(proposal=RENOLD),372).eligible
