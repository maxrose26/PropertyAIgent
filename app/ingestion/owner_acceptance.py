"""Owner-reviewed acceptance of ONE named single-page window (specification 037). Closed, default-off, in reviewed code.

This is NOT source-reconciled completeness and NOT a rule about short pages. The registry below holds exactly one entry, for the Oldham RECEIVED 2026-10-15..21 observation whose audit stays UNKNOWN. A caller can only
NAME the entry (a key string); it cannot supply an acceptance, a file or a hash, so no runtime caller can manufacture an acceptance to bypass completeness. The entry binds the exact source audit, a joint digest of the
complete records, the corroborating calibration evidence, the owner's screenshot (by SHA-256) and the separate times; all identifiers are digests, with no record text. Using it in an execution additionally requires the later
owner-approved package, which seals this entry's digest. Nothing here advances coverage or establishes nominee eligibility.
"""
import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType

from .ledger import Denied, digest

BASIS = 'OWNER_ACCEPTED_SINGLE_PAGE'
SOURCE_BASIS = 'SOURCE_TERMINAL'
BASES = frozenset({SOURCE_BASIS, BASIS})
_ENTRY_SHA256 = '3ca962ff74e426f63b0e5b9a173bda52024a152db03423edcfcf60452b136bcf'      # the digest of the canonical entry below: a change to the entry is a change to this constant and to the test that pins it
_ENTRY = '{"basis":"OWNER_ACCEPTED_SINGLE_PAGE","calibration":{"classification":"ESTABLISHED","code_head":"e30b0806326eb205fd32e877a82dfdb1370cb4a5","code_pull_request":198,"code_tree":"fdb6be9a34fcd1acd1a91d41641ab2f360d49c98","contained_record_count":5,"contained_record_set_sha256":"601c53cd60e86c8090657c6f79ceeb2d94915d06b66fac8002603d729faf5cf4","file_sha256":{"audit.json":"73546b2f24b27e9c58125a6e73ef66905ea9220c4b54fa6404881cbc8471f012","beyond-end.html":"d96bb45da76496e1ae21e57bf4ecb3b8eeab216a48bd2b95a110b07ec9e0f419","control-invalid-page.html":"a0c64873f460338eca04e8579916590949d05cc9a818509256534a238481791b","form.html":"324b976b747ea12362b5af47f83f4581e752eb8f50ff4d30a5f92501b039bc87","page-1.html":"e1af5ef2b26d0a65848fad2050eafa6c9f79931df4c8bf24025b5799ffb7cfa7","page-2.html":"3053c04e35973ab679d43d2aa2d7885c76f74aa11b215f5b97009f2f94014993","registration.json":"76b1ca04ab633af89ad28605e886b9bd1ac9b700620399308d4c8ebf9e0ad761","search.html":"cbeafd7daece0004c842c28f08963a23a0779a6956c6a5dbd44462d0d32696f1","session-check.html":"2835ee91c3aa6c3186932dc547377b6066eef0fbf305c931fbd738c0351fa595"},"identity":"oldham-paging-calibration-20261028-a1","kind":"DIAGNOSTIC_EVIDENCE_NOT_A_REGISTERED_COLLECTION_AUDIT","pages":2,"portal_total":16,"registration_sha256":"76b1ca04ab633af89ad28605e886b9bd1ac9b700620399308d4c8ebf9e0ad761","window_end":"2026-10-21","window_start":"2026-10-08"},"claim":"These five records are the complete result of the council portal RECEIVED-date search for 2026-10-15 to 2026-10-21 as shown by the bound audit and corroborated by the calibration and the owner review. This is OWNER-REVIEWED acceptance, not a source-stated total and not a statement that the council received no other applications.","council":"oldham","end":"2026-10-21","key":"OLDHAM_RECEIVED_20261015_20261021_V1","kind":"OWNER_ACCEPTED_SINGLE_PAGE_WINDOW_V1","limits":["point-in-time acceptance of one window and one audit","corroboration, not a source-stated total","one portal","screenshot is unstructured evidence held by hash","no coverage advance","no nominee eligibility"],"manual_review":{"not_shown":["the searched date criteria"],"screenshot_bytes":279137,"screenshot_sha256":"c57229ec99713bf9c75c35a46180da32d75b60e92eced076cc1a4ffef0287949","shows":["council results page","sort Date Received descending","results per page 100","five applications","bottom of the results list and footer","no pagination controls"]},"semantics":"RECEIVED","source":{"applied_evidence_sha256":"3766b39dbe5ced52cb2b80aa6aa578b4cd36fe8e9b1335f2a4dbabd353f04259","audit_sha256":"97a3fe071da69a7fde32ee7bc663a19d8543c0e49fca5a127415c7e8c7ebc671","enumeration_evidence":"TOTAL_UNKNOWN","evidence_commit":"d0eea18a7a9e1353ff4d281c68dc288dc3363196","evidence_path":"docs/design/ingestion-operational-execution-oldham-metadata-once-20261028/slot-0/source.json","pages":[{"body_sha256":"a9314a7bf1ea0ee9fd512a6d1dec203d92bfd8c77d4e0b4311056be7607596c5","first":null,"last":null,"ordinal":1,"page_size":10,"rows":5,"terminal":null,"total":null}],"record_count":5,"record_set_definition":"ledger digest of the records sorted by reference, each without the informational processing_screen annotation","record_set_sha256":"601c53cd60e86c8090657c6f79ceeb2d94915d06b66fac8002603d729faf5cf4","slot_receipt_sha256":"946e77a942beca6096db367a666e0b864f82a957b71c124ad08209ac30d3382c"},"start":"2026-10-15","times":{"calibration":{"basis":"filesystem times, not source-attested; request times not recorded","private_files_first_written_utc":"2026-10-28T08:54:41+00:00","private_files_last_written_utc":"2026-10-28T08:54:52+00:00","registration_issued_utc":"2026-10-28T08:54:33+00:00"},"manual_review":{"file_name_time":"093601","screen_clock":"09:35 on 28/10/2026","search_criteria_visible":false,"timezone":"NOT_STATED"},"note":"The times are separate observations. No common observation time is claimed and nothing is retrospectively certain.","owner_decision":{"date":"2026-10-28","recorded":"conversation only; no timestamp captured","time":"UNKNOWN"},"source_events_utc":["2026-10-28T06:54:14.800543+00:00","2026-10-28T06:54:16.594003+00:00","2026-10-28T06:54:18.068792+00:00","2026-10-28T06:54:19.266458+00:00"]}}'


@dataclass(frozen=True)
class OwnerAcceptance:
    text: str

    @property
    def data(self):
        return json.loads(self.text)

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def key(self):
        return self.data['key']

    def binding(self):
        return dict(key=self.key, sha256=self.sha256)

    def verify_source(self, source, config):
        """The exact bound audit and nothing else. Any difference refuses; the audit itself is never modified."""
        d = self.data
        s = d['source']
        if (config.council, config.semantics, config.start.isoformat(), config.end.isoformat()) != (d['council'], d['semantics'], d['start'], d['end']):
            raise Denied('OWNER_ACCEPTANCE_SCOPE')
        interval = [d['start'], d['end']]
        if not isinstance(source, dict) or digest(source) != s['audit_sha256']:
            raise Denied('OWNER_ACCEPTANCE_SOURCE_DIGEST')
        if (source.get('council') != d['council'] or source.get('date_semantics') != d['semantics'] or source.get('requested_interval') != interval or source.get('applied_interval') != interval
                or source.get('enumeration_evidence') != s['enumeration_evidence'] or source.get('applied_evidence_sha256') != s['applied_evidence_sha256'] or source.get('failure') is not None
                or source.get('capped') is not False):
            raise Denied('OWNER_ACCEPTANCE_SOURCE_FACTS')
        pages = source.get('pages')
        if (pages != s['pages'] or not isinstance(pages, list) or len(pages) != 1 or any(pages[0].get(k) is not None for k in ('first', 'last', 'total', 'terminal')) or pages[0].get('rows') != s['record_count']):
            raise Denied('OWNER_ACCEPTANCE_PAGE_FACTS')      # exactly the observed single page (the entry's own facts) AND, independently, the shape itself: one page, first, last, total and terminal all null, rows equal to the accepted count
        records = source.get('records')
        if (not isinstance(records, list) or len(records) != s['record_count'] or source.get('unique_references') != s['record_count'] or record_set_digest(records) != s['record_set_sha256']):
            raise Denied('OWNER_ACCEPTANCE_RECORD_SET')
        return self


def record_set_digest(records):
    """The joint digest of the COMPLETE records (identity state, source key, URL, every field state, value and locator), sorted by reference, without the informational processing_screen annotation."""
    clean = [{k: v for k, v in r.items() if k != 'processing_screen'} for r in records]
    return digest(sorted(clean, key=lambda r: r['reference']))


def _load():
    if hashlib.sha256(_ENTRY.encode()).hexdigest() != _ENTRY_SHA256:
        raise RuntimeError('OWNER_ACCEPTANCE_REGISTRY_TAMPERED')
    entry = OwnerAcceptance(_ENTRY)
    return MappingProxyType({entry.key: entry})


ACCEPTANCES = _load()      # read-only; exactly one entry; no function adds to it


def require(key):
    """The registry entry for a KEY STRING. Anything else (an object, a dict, a hash, an unknown key) is refused."""
    if type(key) is not str or key not in ACCEPTANCES:
        raise Denied('OWNER_ACCEPTANCE_UNKNOWN')
    return ACCEPTANCES[key]
