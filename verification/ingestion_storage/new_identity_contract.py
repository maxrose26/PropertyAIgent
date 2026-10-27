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


# Modules whose bytes define the Arcus projection. They are bound into the factual hash, so a change to any of them can never silently share an identity.
ARCUS_PROJECTION_MODULES = ('verification.direct_reference.arcus_adapter', 'verification.direct_reference.arcus_transport')


def project_arcus(row, source):
    """The existing Arcus exact-record projection, as a NewIdentityContract projector: the committee route's own `_qualify_row` / `_from_observed_row`, unchanged.

    The initial-status scope is selected exactly as `committee_exact.retrieve` selects it (Manchester `Under Consideration`, Salford `Under Consultation`); any other state
    stays unsupported and the admission is withheld by the shared gate. No retrieval, parser or writer is added; `source` is a supervised detail audit supplied by the caller.
    """
    from verification.direct_reference.arcus_adapter import _from_observed_row
    from verification.direct_reference.arcus_transport import _qualify_row
    worker_row = dict(row, application_id=None)
    def project(observed):
        state = observed.get('record_field_states', {}).get('status', {}).get('value')
        return _from_observed_row(worker_row, observed, initial_status=state in {'Under Consideration', 'Under Consultation'})
    return _qualify_row(None, source, worker_row, row['case'], project)


def accepted_arcus_new_identity(name, row, *, verification_scope='INITIAL_STATUS_ONLY'):
    # The same B2 completeness/semantic predicate and the same shared handoff as Idox; only the projector differs.
    return NewIdentityContract(name, row, project_arcus, _refresh_row, qualified_coupled_observation, verification_scope)
