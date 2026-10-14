from verification.bolton_recon.discovery_form_shape import inspect_form


def test_form_shape_never_releases_token_or_private_defaults():
    body = b'''<html><form><input name="date(applicationReceivedStart)">
    <input type="hidden" name="_csrf" value="TOP-SECRET">
    <input name="searchCriteria.applicantName" value="PRIVATE PERSON">
    <input type="hidden" name="searchType" value="Application">
    </form></html>'''
    rows = inspect_form(body)
    assert rows[1]['neutral_default'] is None
    assert rows[2]['neutral_default'] is None
    assert rows[3]['neutral_default'] == 'Application'
    assert 'TOP-SECRET' not in repr(rows)
    assert 'PRIVATE PERSON' not in repr(rows)


def test_untrusted_input_type_is_bounded():
    body = b'<html><form><input name="date(applicationReceivedStart)"><input type="' + b'PRIVATE' * 1000 + b'"></form></html>'
    assert inspect_form(body)[1]['kind'] == 'UNKNOWN'
