from datetime import datetime, timedelta, timezone
import pytest
from app.pipeline.discovery_acceptance import ReferenceEntry as R, DetectionEntry as D, reconcile
T=datetime(2026,10,14,tzinfo=timezone.utc)


def test_independent_miss_cannot_be_hidden_by_manual_addition():
    refs=[R('bolton','A/26','CONFIRMED_MATERIAL',True,'manual-list:1'),R('bolton','B/26','POTENTIALLY_MATERIAL',True,'manual-list:2')]
    detected=[D('bolton','A/26',T,'primary:1',True,True,False),D('bolton','B/26',T,'manual-addition',False,False,True)]
    result=reconcile(refs,detected,frozenset(),complete_councils={'bolton'},comparison_at=T)
    assert [r['outcome'] for r in result['references']]==['WITHHELD_AFTER_DETECTION','MISSED']
    assert result['observed_material_misses']==1
    assert result['unexplained_material_misses'] is None
    assert result['councils']['bolton']['CONFIRMED_MATERIAL']['recall']==1
    assert result['councils']['bolton']['CONFIRMED_MATERIAL']['admitted']==0
    assert result['acceptance_claim'] is False


def test_unknown_denominator_and_zero_do_not_become_perfect_recall():
    refs=[R('bolton','A/26','CONFIRMED_MATERIAL',True,'list:1')]
    result=reconcile(refs,[D('bolton','A/26',T,'primary',True,False,True)],frozenset(),complete_councils=set(),comparison_at=T)
    assert result['councils']['bolton']['CONFIRMED_MATERIAL']['recall'] is None
    assert result['councils']['bury']['POTENTIALLY_MATERIAL']['recall'] is None


def test_overlap_known_outside_and_publication_latency_are_separate():
    refs=[R('bolton','A/26','POTENTIALLY_MATERIAL',True,'list:1',T-timedelta(days=8)),
          R('bolton','B/26','CONFIRMED_MATERIAL',True,'list:2'),R('bolton','C/26','CONFIRMED_MATERIAL',False,'list:3')]
    detections=[D('bolton','A/26',T-timedelta(days=2),'first',True,False,False),D('bolton','A/26',T,'overlap',True,False,True)]
    result=reconcile(refs,detections,frozenset({('bolton','B/26')}),complete_councils={'bolton'},comparison_at=T)
    a,b,c=result['references']
    assert a['latency_seconds']==6*86400 and a['within_seven_days'] is True and a['admitted']
    assert b['outcome']=='ALREADY_KNOWN' and b['latency_seconds'] is None
    assert c['outcome']=='OUTSIDE_INTERVAL'
    with pytest.raises(ValueError):reconcile(refs, detections+[D('bolton','A/26',T+timedelta(seconds=1),'late',True,False,True)],frozenset(),complete_councils=set(),comparison_at=T)


def test_seven_calendar_days_across_clock_change():
    from zoneinfo import ZoneInfo
    from app.pipeline.discovery_contract import latency_seconds
    london=ZoneInfo('Europe/London')
    published=datetime(2026,10,21,12,tzinfo=london)
    detected=datetime(2026,10,28,12,tzinfo=london)
    assert latency_seconds(detected,published)==169*3600
    assert latency_seconds(detected.astimezone(timezone.utc),published.astimezone(timezone.utc))==169*3600
    refs=[R('bolton','A/26','CONFIRMED_MATERIAL',True,'publication',published)]
    result=reconcile(refs,[D('bolton','A/26',detected,'primary',True,False,True)],frozenset(),complete_councils={'bolton'},comparison_at=detected)
    assert result['references'][0]['within_seven_days'] is True
    late=detected+timedelta(seconds=1)
    result=reconcile(refs,[D('bolton','A/26',late,'primary',True,False,True)],frozenset(),complete_councils={'bolton'},comparison_at=late)
    assert result['references'][0]['within_seven_days'] is False
