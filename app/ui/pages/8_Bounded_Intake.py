"""Owner-only fixed pilot control. No reader, credential prompt or business logic."""
import streamlit as st
import time
from app.ui.access import page_scope
from app.security.access import load_policy,AccessDenied,require_operator

with page_scope() as actor:
    require_operator('administration.read')
    policy=load_policy()
    if actor.machine or (actor.issuer,actor.subject)!=(policy['issuer'],policy['owner_subject']):
        raise AccessDenied('Owner access required.')
    from app.owner_intake_control import start,status
    st.title('Bounded planning intake')
    st.write('One approved pilot: 27 October–2 November 2026, inclusive. Tameside uses received dates; Manchester uses validated dates. Listing metadata, deterministic screening and durable backlog only.')
    st.caption('Tameside: 10 requests, 3,000,000 bytes, six pages of five (30 listings), 45 source seconds. Manchester: 80 requests, 20 MiB, 60 listings, six pages, 75 source seconds. Aggregate runtime: 960 seconds. GitHub publication is not requested.')
    result=status();st.json(result)
    prepared=result.get('status')=='ARTIFACT_READY'
    def record_boundary():
        st.session_state['pilot_boundary_checked_at']=time.time() if st.session_state.get('pilot_boundary_checked') else None
    checked=st.checkbox('I have checked the scraper Dashboard now: no linked environment groups; all other ingestion, configuration and privilege activity is stopped and will remain stopped for this pilot. Do not change or save anything in the Dashboard.',key='pilot_boundary_checked',on_change=record_boundary)
    observed=st.session_state.get('pilot_boundary_checked_at')
    fresh=checked and type(observed) in (int,float) and 0<=time.time()-observed<=300
    if st.button('Run approved Manchester/Tameside pilot',disabled=not prepared or not fresh,type='primary'):
        # Recheck the existing native lease at the actual launch boundary.
        require_operator('administration.read')
        start('run',owner_checked=True,checked_at=observed)
        st.success('The bounded pilot has started. This page can be refreshed; recovery state is retained privately in PostgreSQL.')
    if st.button('Close access and restore pilot environment',disabled=result.get('status') in ('NOT_PREPARED','CLOSED')):
        require_operator('administration.read');start('recover')
        st.info('Independent containment started. This action does not collect or replay listings.')
    st.caption('A failed, incomplete or OPEN run is not success. Use the recovery control if the run is interrupted. The one-use record prevents another collection attempt.')
