"""Offline intake bounds and inactive CLI; no source, DB or credential access."""
from datetime import datetime, timezone
import pytest
from app.ingestion.daily_intake import current_windows, inactive_main
from app.ingestion.ledger import Denied


def test_current_intake_does_not_wait_for_historical_recovery():
    rows=current_windows(datetime(2026,10,29,tzinfo=timezone.utc),['bolton','manchester'])
    assert rows==[dict(council='bolton',semantics='RECEIVED',start='2026-10-22',end='2026-10-28'),
                  dict(council='manchester',semantics='VALIDATED',start='2026-10-22',end='2026-10-28')]


def test_local_completed_day_not_utc_day():
    row=current_windows(datetime(2026,7,1,23,30,tzinfo=timezone.utc),['bolton'],overlap_days=1)[0]
    assert row['start']==row['end']=='2026-07-01'


@pytest.mark.parametrize('councils,days',[(['trafford'],7),(['bolton','bolton'],7),([],7),(['bolton'],29),(['bolton'],True),
                                            (['bolton','bury','oldham','tameside'],7)])
def test_unsupported_capacity_and_scopes_refuse(councils,days):
    with pytest.raises(Denied):current_windows(datetime.now(timezone.utc),councils,overlap_days=days)


def test_default_command_cannot_fall_back_to_legacy(capsys):
    assert inactive_main()==2
    import json
    result=json.loads(capsys.readouterr().out)
    assert result['database_connections']==result['source_requests']==result['application_writes']==0
    assert result['reason']=='EXPLICIT_INTAKE_PERIOD_REQUIRED'


def test_capture_bound_worker_is_an_explicit_reversible_extension():
    from verification.ingestion_storage import screening_v3_worker_sql as v3
    historical=v3.derive()
    current=v3.capture_bound_text(historical)
    for old,new in reversed(v3.capture_bound_sites()):
        assert current.count(new)==1
        current=current.replace(new,old)
    assert current==historical


def test_capture_bound_revision_reuses_existing_observation_contract():
    from app.ingestion.observation_screening import observation_revision
    from app.ingestion.ledger import digest
    assessment='a'*64
    first,second=observation_revision(assessment,'b'*64),observation_revision(assessment,'c'*64)
    assert first!=second
    assert first==digest(dict(assessment_revision=assessment,observation_sha256='b'*64))
