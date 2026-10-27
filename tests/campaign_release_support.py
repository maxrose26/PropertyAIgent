"""Reconstructed HTML/locator fixtures only. No real council markup, source or authority."""
import asyncio
from datetime import date,timedelta
from unittest.mock import patch
from verification.discovery import campaign_manifest as campaign,finite_acceptance as finite,four_council_proof as proof
from tests.test_discovery_four_council_proof import bodies,run,async_run,RenderedPage
from verification.discovery import arcus_ui_window as ui
from verification.discovery.arcus_ui_config import ROCHDALE,dated_config


def selection(start='2026-11-01',end='2026-11-07',councils=('oldham','rochdale','tameside')):
    plan=finite.manifest(start,end,'PROSPECTIVE')
    return dict(finite_manifest=plan,finite_manifest_sha256=finite.digest(plan),selected_ordinals=[i for i,r in enumerate(plan['rows']) if r['council'] in councils])


def audit(row,*,complete=True,local=None):
    with proof.manifest_scope(row):
        scope=tuple(row[k] for k in ('council','semantics','start','end'))
        if row['council']!='rochdale':
            values=bodies(scope,pager=complete)
            if local=='selector':values=[values[0],b'<html><form></form></html>']
            if local=='timeout':
                import requests
                values=values[:2]+[requests.Timeout('SYNTHETIC_PRIVATE_TEXT')]
            from tests.test_discovery_four_council_proof import config
            from tests.test_discovery_idox_window import Response
            from verification.discovery import idox_window
            values=iter(values)
            class Session:
                closed=False
                def __enter__(self):return self
                def __exit__(self,*_):self.closed=True
                def mount(self,*_):pass
                def request(self,*args,**kwargs):
                    value=next(values)
                    if isinstance(value,Exception):raise value
                    return Response(value)
            session=Session()
            with patch.object(idox_window.requests,'Session',return_value=session),patch.object(idox_window.time,'sleep',lambda _:None):
                value=idox_window.live(config(scope),retain_proof=True)
            assert session.closed
            return value
        cfg=dated_config(ROCHDALE,row['start'],row['end'])
        from tests.test_discovery_arcus_ui import card
        from verification.discovery.execution_budget import Deadline,select
        async def cards(page,config):
            value=card('SYNTHETIC/1',key='a'*18,valid=date.fromisoformat(config.start).strftime('%d/%m/%Y'))
            value['links'][0]['href']=value['links'][0]['href'].replace('arcusbe.manchester.gov.uk',config.host)
            return [value]
        value=dict(case='discovery_rochdale_ui_window',destination=cfg.destination,persistence=False,
            requested_interval=[cfg.start,cfg.end],date_semantics='VALIDATED',requests=2,decoded_bytes=1000,encoded_bytes=1000,outbound_payload_bytes=0,
            cleanup='CONTEXT_BROWSER_CLOSED',process_cleanup='CLOSED',live_owned_survivors=0,supervisor_seconds=.01,supervisor_limit_hit=False,pages=1,navigations=1,
            public_ui_posts=1,measured_public_ui_posts=1,failure=None,safety_failure=False,safety_events=[],accounting_complete=True,
            execution_budget='BROWSER_SOURCE_V2',stage_timings={'NAVIGATION':1})
        with patch.object(ui,'read_cards',cards):
            async_run(ui.enumerate_ui(RenderedPage(cfg,failure=bool(local),total=1),value,asyncio.Event(),cfg,retain_proof=True,
                budget=select('BROWSER_SOURCE_V2'),deadline=Deadline(70)))
        if local:
            from verification.direct_reference.instrumented_probe import classify_ui_enumeration
            classify_ui_enumeration(value,lambda reason:(_ for _ in ()).throw(AssertionError(reason)))
            value.update(containment_accounting_verified=True,requested_origins=['https://'+cfg.host],navigated_origins=['https://'+cfg.host],navigation_mismatch=None,
                blocked_actions=[],blocked_action_metadata=[],blocked_posts=0)
        return value
