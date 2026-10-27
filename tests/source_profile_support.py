"""Synthetic inputs to real readers; NOT real council qualification."""
import asyncio
from datetime import date,timedelta
from unittest.mock import patch
from verification.discovery import finite_acceptance as finite, four_council_proof as proof, source_profiles as profiles
from verification.discovery import arcus_ui_window as ui, idox_window
from tests.campaign_release_support import selection as old_selection
from tests.e2e_connection_support import _idox_form,_idox_page,_Response,entry,SCHEME
from tests.test_discovery_four_council_proof import RenderedPage,async_run
from tests.test_discovery_screening_assessment import Fields,immediate
from verification.discovery.screening_capture import capture_fields


def selection(councils=('bolton','manchester','stockport'),mode='SCREENING_METADATA',start='2026-11-01',end='2026-11-07'):
    return dict(old_selection(start,end,councils),collection_mode=mode)


def registration(value=None):
    from verification.discovery import four_council_release as r
    t=r.now()-timedelta(minutes=1)
    return r.render('profile-offline-fixture','a'*40,'b'*40,'1'*40,t.isoformat(),(t+timedelta(hours=2)).isoformat(),released=True,
        version=r.PROFILED_CAMPAIGN_VERSION,campaign=selection() if value is None else value)


def audit(row,mode='SCREENING_METADATA'):
    p=profiles.profile(row,mode)
    with proof.manifest_scope(row,p):
        start,end=map(date.fromisoformat,(row['start'],row['end']))
        if p['family']=='IDOX':
            cfg=idox_window.WindowConfig(row['council'],row['semantics'],start,end,max_transport_retries=0,max_rows=60)
            entries=[entry('SYNTHETIC/1',SCHEME)]
            page=_idox_page(row['council'],entries,start,end)
            values=iter([_idox_form(row['semantics']),page,page,_idox_form(row['semantics'],start.strftime('%d/%m/%Y'),end.strftime('%d/%m/%Y'))])
            class Session:
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def mount(self,*_):pass
                def request(self,*args,**kwargs):return _Response(next(values))
            with patch.object(idox_window.requests,'Session',return_value=Session()),patch.object(idox_window.time,'sleep',lambda _:None):
                value=idox_window.live(cfg,retain_proof=True)
        else:
            cfg=profiles.config(p)
            async def cards(page,config):
                card=dict(fields=[dict(label='Reference',value='SYNTHETIC/1')],links=[dict(text='SYNTHETIC/1',href='https://'+cfg.host+'/pr/s/detail/'+'a'*18+'?c__r=Arcus_BE_Public_Register')])
                if cfg.row_date:card['fields'].append(dict(label='Valid Date',value=start.strftime('%d/%m/%Y')))
                if cfg.assessment_metadata:
                    card['assessment_capture']=immediate(capture_fields(Fields(['Description\n'+SCHEME,'Site Address\n1 Synthetic Street'])))
                return [card]
            value=dict(case=p['case'],destination=p['destination'],persistence=False,
                requested_interval=[cfg.start,cfg.end],date_semantics='VALIDATED',requests=2,decoded_bytes=1000,encoded_bytes=1000,outbound_payload_bytes=0,
                cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,supervisor_seconds=.01,supervisor_limit_hit=False,pages=1,navigations=1,
                public_ui_posts=1,measured_public_ui_posts=1,failure=None,safety_failure=False,safety_events=[],accounting_complete=True,
                execution_budget='BROWSER_SOURCE_V2',stage_timings={'NAVIGATION':1},peak_owned_rss=100)
            from verification.discovery.execution_budget import Deadline,select
            with patch.object(ui,'read_cards',cards):
                async_run(ui.enumerate_ui(RenderedPage(cfg,failure=False,total=1),value,asyncio.Event(),cfg,retain_proof=True,
                    budget=select('BROWSER_SOURCE_V2'),deadline=Deadline(70)))
        return profiles.bind_audit(p,value)
