from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.scrapers import arcus_portal, idox_portal


def page():
    p = Mock()
    p.locator.return_value.count.return_value = 1
    p.locator.return_value.first.evaluate.return_value = ''
    p.eval_on_selector_all.return_value = []
    p.inner_text.return_value = 'Reference\n123/26\nSite address\nA\nDescription\n100 dwellings\nStatus\nPending'
    p.content.return_value = '<html><body><a href="applicationDetails.do?keyVal=X">Application</a></body></html>'
    p.url = 'https://paplanning.bolton.gov.uk/online-applications/advancedSearchResults.do'
    return p


def test_arcus_exception_does_not_return_partial(monkeypatch):
    p = page()
    p.locator.return_value.first.click.side_effect = RuntimeError('navigation failed')
    with pytest.raises(RuntimeError, match='incomplete'):
        arcus_portal._walk_result_pages(p)


def test_arcus_cap_does_not_return_partial(monkeypatch):
    monkeypatch.setattr(arcus_portal, 'MAX_PAGES_PER_SEARCH', 2)
    with pytest.raises(RuntimeError, match='cap'):
        arcus_portal._walk_result_pages(page())


def test_arcus_conflicting_duplicate(monkeypatch):
    p = page()
    p.inner_text.side_effect = ['Reference\n123/26\nStatus\nPending',
                                'Reference\n123/26\nStatus\nGranted']
    with pytest.raises(RuntimeError, match='conflicting duplicate'):
        arcus_portal._walk_result_pages(p)


def test_idox_exception_does_not_return_partial(monkeypatch):
    p = page()
    p.locator.return_value.first.click.side_effect = RuntimeError('navigation failed')
    monkeypatch.setattr(idox_portal.time, 'sleep', lambda _: None)
    cfg = SimpleNamespace(search_url=p.url, date_start_field='start', date_end_field='end')
    with pytest.raises(RuntimeError, match='incomplete'):
        idox_portal.collect_result_links(p, cfg, '01/10/2026', '07/10/2026')


def test_idox_cap_does_not_return_partial(monkeypatch):
    p = page()
    monkeypatch.setattr(idox_portal.time, 'sleep', lambda _: None)
    cfg = SimpleNamespace(search_url=p.url, date_start_field='start', date_end_field='end')
    with pytest.raises(RuntimeError, match='cap'):
        idox_portal.collect_result_links(p, cfg, '01/10/2026', '07/10/2026')
