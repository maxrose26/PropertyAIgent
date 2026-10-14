from datetime import date
import pytest
from app.scrapers.discovery_idox import parse_page, ListingError
D=date(2026,9,28)


def page(first=1,last=2,total=2,refs=('001/26','002/26'),next_page=None,pager=True):
    rows=''.join(f'<li class="searchresult"><a class="summaryLink" href="applicationDetails.do?keyVal=K{i}&amp;activeTab=summary">Outline residential development, scale unknown</a><p class="address"></p><p class="metaInfo">Ref. No: {r} · Received: Mon 28 Sep 2026 · Validated: Mon 28 Sep 2026</p></li>' for i,r in enumerate(refs))
    nxt=f'<a class="next" href="pagedSearchResults.do?action=page&amp;searchCriteria.page={next_page}">Next</a>' if next_page else ''
    p=f'<p class="pager">Showing {first}-{last} of {total}{nxt}</p>' if pager else ''
    return f'<html><h1>Planning – Results for Application Search</h1><select id="resultsPerPage"><option value="10" selected>10</option></select>{p}<ul id="searchresults">{rows}</ul></html>'.encode()


def test_displayed_reference_and_sparse_fields():
    p=parse_page(page(), 'bolton',1,D,D)
    assert [r.reference for r in p.rows]==['001/26','002/26']
    assert p.rows[0].fields['address'].state=='PRESENT_BLANK'
    assert p.rows[0].fields['received_date'].value=='Mon 28 Sep 2026'
    assert p.terminal=='EXPLICIT_LAST_EQUALS_TOTAL'
    assert p.next_url is None


def test_missing_total_cannot_prove_completeness():
    p=parse_page(page(pager=False),'bolton',1,D,D)
    assert p.total is None and p.terminal is None


@pytest.mark.parametrize('body',[
    page(total=20), page(total=2,next_page=2),page(first=2,last=3,total=3),
    page().replace(b'</html>',b''),page().replace(b'28 Sep',b'29 Sep'),
    page().replace(b'keyVal=K1',b'keyVal=K0'),
    page().replace(b'applicationDetails.do?',b'https://evil.example/applicationDetails.do?'),
])
def test_fail_closed_structure_counts_date_identity_and_origin(body):
    with pytest.raises(ListingError): parse_page(body,'bolton',1,D,D)


def test_conflicting_identity_preserved_not_url_inferred():
    body=page(refs=('001/26','002/26')).replace(b'Ref. No: 001/26',b'Ref. No: 001/26 \xc2\xb7 Ref. No: 999/26')
    p=parse_page(body,'bolton',1,D,D)
    assert p.rows[0].reference is None and p.rows[0].identity_state=='CONFLICTING'


def test_sequential_page_link_and_count():
    p=parse_page(page(first=11,last=12,total=12),'bolton',2,D,D)
    assert p.terminal=='EXPLICIT_LAST_EQUALS_TOTAL'
    with pytest.raises(ListingError): parse_page(page(first=11,last=12,total=12),'bolton',1,D,D)


def test_same_reference_distinct_source_keys_withheld():
    p=parse_page(page(refs=('001/26','001/26')),'bolton',1,D,D)
    assert all(r.reference is None and r.identity_state=='CONFLICTING' for r in p.rows)


def test_bury_observed_link_key_and_pipe_separator():
    body=page(refs=('73718','73716')).replace(b'class="summaryLink"',b'').replace(b'keyVal=K0',b'keyVal=_BURY_DCAPR_65225').replace(b'keyVal=K1',b'keyVal=_BURY_DCAPR_65221').replace('·'.encode(),b'|')
    p=parse_page(body,'bury',1,D,D)
    assert [r.reference for r in p.rows]==['73718','73716']
    assert p.rows[0].source_key=='_BURY_DCAPR_65225'
    assert p.rows[0].fields['received_date'].state=='PRESENT_VALUE'
    with pytest.raises(ListingError):parse_page(body.replace(b'_BURY_DCAPR_65225',b'_ARBITRARY_65225'),'bury',1,D,D)


def test_explicit_zero_is_not_an_empty_or_error_page():
    from app.scrapers.discovery_idox import explicit_zero
    b='<html><h1>Planning – Applications Search</h1><div class="messagebox"><h2>Please check the search criteria:</h2><ul><li>No results found.</li></ul></div></html>'.encode()
    assert explicit_zero(b,'bury')
    assert not explicit_zero(b,'bolton')
    assert not explicit_zero(b'<html><h1>Error</h1></html>','bury')
    with pytest.raises(ListingError):explicit_zero(b.replace(b'</ul>',b'<li>Invalid date</li></ul>'),'bury')
    with pytest.raises(ListingError):explicit_zero(b.replace(b'</html>',b''),'bury')


def test_zero_rejects_separate_error_list_or_messagebox():
    from app.scrapers.discovery_idox import explicit_zero
    b='<html><h1>Planning – Applications Search</h1><div class="messagebox"><h2>Please check the search criteria:</h2><ul><li>No results found.</li></ul></div></html>'.encode()
    for extra in (b'<ul><li>Invalid date</li></ul>',b'<div class="messagebox"><ul><li>Invalid date</li></ul></div>'):
        changed=b.replace(b'</div></html>',extra+b'</div></html>')
        with pytest.raises(ListingError):explicit_zero(changed,'bury')
