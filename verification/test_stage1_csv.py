import csv
import io
import pytest
import pandas as pd
from app.reporting.csv_safety import safe_cell, safe_dataframe, csv_bytes


@pytest.mark.parametrize('value', ['=1+1', '+SUM(A1)', '-1+2', '@SUM(A1)', '\ttext', '\rtext', '\ntext', '  =1+1', '\ufeff=1', '＝1+1', '＋1', '－1', '＠x', '\x00=1', '+44 1234'])
def test_external_formula_text(value):
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize('value', [-12, 0, 12.5, None, True, 'ordinary', 'https://planning.stockport.gov.uk/PlanningData-live', 'quoted,"value"\nnext', '72', ''])
def test_legitimate_typed_values(value):
    assert safe_cell(value) == value


def test_csv_quotes_headers_and_source_unchanged():
    source = {'=header': '=1+1', 'id': 78, 'units': -12, 'source': 'a,"b"\nnext'}
    result = list(csv.reader(io.StringIO(csv_bytes([source], list(source)).decode())))
    assert result == [["'=header", 'id', 'units', 'source'], ["'=1+1", '78', '-12', 'a,"b"\nnext']]
    assert source['=header'] == '=1+1'


def test_dataframe_download_projection_preserves_index_and_source():
    raw = pd.DataFrame({'id': [78], 'text': ['=1+1'], 'units': [-12]}, index=[8])
    safe = safe_dataframe(raw)
    assert safe.loc[8, 'text'] == "'=1+1"
    assert safe.loc[8, 'id'] == 78
    assert safe.loc[8, 'units'] == -12
    assert raw.loc[8, 'text'] == '=1+1'
