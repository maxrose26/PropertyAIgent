"""Bounded recorded Idox transport. No network client or live fallback."""
import time
from bs4 import BeautifulSoup
from app.scrapers.documents import _find_document_links


class Deferred(RuntimeError):
    pass


class RecordedIdox:
    def __init__(self, recordings, deadline, *, requests=8, body_limit=4096, total_bytes=16384):
        if min(requests, body_limit, total_bytes) <= 0:
            raise ValueError("limits must be positive")
        self.recordings, self.deadline = recordings, deadline
        self.requests, self.body_limit, self.total_bytes = requests, body_limit, total_bytes
        self.calls = self.bytes = 0

    def read(self, name):
        if time.monotonic() >= self.deadline or self.calls >= self.requests or self.bytes >= self.total_bytes:
            raise Deferred('request/time budget')
        self.calls += 1
        response = self.recordings.get(name)
        if response is None:
            raise RuntimeError('recording unavailable; no live fallback')
        if response['status'] != 200:
            raise RuntimeError('body not verified: HTTP ' + str(response['status']))
        # Chunks model decoded streaming bytes; account even for aborted bodies.
        body = bytearray()
        for chunk in response['chunks']:
            if time.monotonic() >= self.deadline:
                raise Deferred('stream deadline')
            remaining = min(self.body_limit-len(body), self.total_bytes-self.bytes)
            # Detect oversize with at most one sentinel byte, never retain it.
            self.bytes += min(len(chunk), remaining + 1)
            if len(chunk) > remaining:
                raise Deferred('stream byte budget; not checked')
            body.extend(chunk)
        return bytes(body)

    def fetch(self, ticket):
        prefix = ticket['council'] + '/' + ticket['reference']
        cursor = ticket['cursor']
        if ticket['stage'] == 'documents':
            # One register response, then one body per checkpoint: partial work
            # survives inaccessible later PDFs. Re-list on restart; URL dedup is
            # not body verification. Fixture listing must be explicitly complete.
            html = self.read(prefix + '/register').decode()
            soup = BeautifulSoup(html, 'html.parser')
            if soup.find('table') is None or soup.find('a', attrs={'rel':'next'}):
                raise RuntimeError('unrecognised/incomplete register recording')
            docs = _find_document_links(soup, 'https://recorded.invalid/', 'https://recorded.invalid/register')
            urls = [d.source_url for d in docs]
            snapshot = __import__('hashlib').sha256(html.encode()).hexdigest()
            if cursor == 'start':
                index = 0
            else:
                old, index = cursor.split(':'); index = int(index)
                if old != snapshot:
                    raise RuntimeError('register changed; explicit restart required')
            if not docs:
                return {'cursor':cursor,'next':None,'documents':[]}
            if index >= len(docs):
                raise RuntimeError('invalid register cursor')
            selected = docs[index]
            body = self.read(selected.source_url)
            next_cursor = snapshot + ':' + str(index+1) if index+1 < len(docs) else None
            return {'cursor':cursor,'next':next_cursor,'documents':[dict(
                council=ticket['council'],reference=ticket['reference'],url=selected.source_url,
                body=body,title=selected.document_name,stage='unreviewed_document',
                issued=None,published=None,proposed={})]}
        # Relationship results explicitly record parsed references/citations.
        # This is a transport-boundary recording contract, not a claim that
        # live Idox HTML exposes these attributes or that search recall is proven.
        data = __import__('json').loads(self.read(prefix + '/relationships/' + cursor))
        if 'edges' not in data or 'next' not in data:
            raise RuntimeError('incomplete relationship recording')
        return dict(data, cursor=cursor)
