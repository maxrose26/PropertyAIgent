"""Offline canary acceptance checks only; not planning verification or dependency inference."""
from app.reporting.subject_relationships import scan_parent_citations
import minimum

def check_canary_coverage(capture):
    if capture['retrieval_state']!='COMPLETE' or capture['dependency_census_state']!='QUALIFIED':
        raise ValueError('Unexpected capture qualification')
    data=capture['data'];apps={a['id']:a for a in data['applications']}
    if {s['id'] for s in data['sites']}!=set(minimum.COHORT):
        raise ValueError('Wrong or incomplete six-site cohort')
    for site,app,ref in [(25,29,'FUL/355201/25'),(28,42,'FUL/355686/26'),
        (254,305,'117614/FUL/25'),(58,78,'DC/078942'),
        (179,284,'NOT/2026/0722'),(179,566,'23/81719/HYBEIA'),
        (281,358,'VAR/349651/22'),(281,737,'OUT/345898/20')]:
        if app not in apps or (apps[app]['site_id'],apps[app]['reference'])!=(site,ref):
            raise ValueError('Required exact canary application missing or changed')
    child,parent=apps[284],apps[566]
    if child['council_code']!=parent['council_code'] or child['application_category']!='reserved_matters':
        raise ValueError('Retained parent/RM context no longer established')
    citations=scan_parent_citations(child['proposal']).qualifying
    if [c.reference for c in citations]!=[parent['reference']]:
        raise ValueError('Missing or ambiguous exact statutory parent citation')
    # Neither record supplies any verification field to the other.
    return dict(parent_rm_context='EXACT_CITATION_AND_SEPARATE_RECORDS',
        parent_verified_at=parent['status_verified_at'],child_verified_at=child['status_verified_at'],
        acquisition_containment='NOT_ESTABLISHED',
        direct_context_discovery='Requires accepted consumer attribution; no promotion by site membership',
        current_planning_source_truth='NOT_REVERIFIED')
