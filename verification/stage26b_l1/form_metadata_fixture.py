"""SYNTHETIC transport expectations, not retained/current Oldham evidence."""
BODY = b'''<html><form action="/ignored" method="get"><input name="unrelated"></form>
<form action="/online-applications/advancedSearchResults.do?action=firstPage" method="post">
<input type="hidden" name="_csrf" value="HIDDEN_SECRET_MARKER">
<input name="searchCriteria.reference" value="">
<input name="searchCriteria.applicantName" value="PRIVATE_APPLICANT_MARKER">
<input name="searchCriteria.address" value="PRIVATE_ADDRESS_MARKER">
<input name="searchCriteria.postcode" value="PRIVATE_POSTCODE_MARKER">
<input name="searchCriteria.proposal" value="PRIVATE_PROPOSAL_MARKER">
<input name="searchCriteria.dateFrom" value="PRIVATE_DATE_MARKER" type="date">
<input name="searchCriteria.dateTo" value="">
<select name="searchCriteria.status"><option value="OPTION_SECRET_MARKER" selected>PRIVATE_LABEL</option><option value="SECOND_SECRET">OTHER</option></select>
<input name="searchCriteria.ward" type="checkbox" value="CHECKBOX_SECRET" checked>
<input name="searchCriteria.parish" type="radio" value="RADIO_SECRET">
<input type="submit" name="action" value="Search">
<input name="searchCriteria.keyword" disabled value="DISABLED_SECRET">
<input name="searchCriteria.agent" value=""><input name="searchCriteria.agent" value="DUPLICATE_SECRET">
<input name="x7_f7ac80bc60e0876c7b438_secret" value="TOKEN_VALUE_SECRET">
<input name="oversized_identifier_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" value="LONG_SECRET">
<textarea name="searchCriteria.description">TEXTAREA_PRIVATE_MARKER</textarea>
<input type="hidden" name="searchType" value="Application">
</form></html>'''


class Response:
    def __init__(self, body=BODY, status=200):
        self.body, self.status_code, self.closed = body, status, False
        self.raw = None

    def iter_content(self, size):
        for i in range(0, len(self.body), size): yield self.body[i:i+size]

    def close(self): self.closed = True


def fixture_response(method, url, **kwargs):
    from .form_metadata import URL
    assert method == 'GET' and url == URL
    assert kwargs == dict(allow_redirects=False, stream=True, timeout=15)
    return Response()
