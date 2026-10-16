"""Bind existing qualified factual components outside application runtime imports.

No source transport, live registration, credential discovery or new semantics.
"""
from app.ingestion.new_identity import NewIdentityContract
from verification.discovery.material_qualification import project_idox
from verification.direct_reference.refresh import _refresh_row
from verification.stage26b_l1.bolton_literal import semantic_state

def qualified_coupled_observation(observation, row):
    """Existing B2 completeness/semantic predicate, reused before admission."""
    return observation.verification_scope == 'COUPLED' and not (set(observation.fields) != {'Reference','Status','Decision','Decision Issued Date'}
                or observation.fields['Reference'] != row['reference']
                or set(observation.field_states) != {'reference','status','decision','decision_date'}
                or any(v not in {'PRESENT_VALUE','PRESENT_BLANK'} for v in observation.field_states.values())
                or observation.field_states['reference'] != 'PRESENT_VALUE'
                or observation.field_states['status'] != 'PRESENT_VALUE'
                or semantic_state(observation.fields) == 'UNKNOWN_UNMAPPED'
                or not observation.b2_eligible)


def accepted_idox_new_identity(name,row,*,verification_scope='COUPLED'):
    return NewIdentityContract(name,row,project_idox,_refresh_row,qualified_coupled_observation,verification_scope)
