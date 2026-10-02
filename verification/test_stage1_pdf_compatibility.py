import pandas as pd
from app.reporting.pdf_report import compute_aggregate_stats,build_narrative_prompt,render_pdf

def frame():
    return pd.DataFrame([{'Total Units':20,'Affordable Units':10,'Reported Private Units (unverified legacy scope)':999,'decision_status':'granted','lapse_status':'unknown','Council':'stockport','Developer':None,'Address':'Synthetic','References':'SYN/1'}])

def test_missing_qualified_private_column_is_unknown_not_legacy_or_derived():
    data=frame();stats=compute_aggregate_stats(data)
    assert stats.total_private_units is None
    assert stats.total_affordable_units==10 and stats.total_units==20
    prompt=build_narrative_prompt(stats,None)
    assert 'Total private units: unknown (no qualified private-unit count)' in prompt
    assert '999' not in prompt
    assert render_pdf(data.to_dict('records'),stats,{}).startswith(b'%PDF')

def test_existing_qualified_private_column_preserved():
    data=frame();data['Private Units']=7
    stats=compute_aggregate_stats(data)
    assert stats.total_private_units==7
    assert 'Total private units: 7' in build_narrative_prompt(stats,None)
