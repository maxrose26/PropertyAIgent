"""Closed retained policy-due Arcus scope, excluding the manual candidate."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs

MANIFEST_SHA256 = '839ebb2762083154ada81dbc9124cf4143b913d52845ba4567b6c14706b18e32'
ORIGINS = {'manchester': 'arcusbe.manchester.gov.uk',
           'rochdale': 'account.rochdale.gov.uk',
           'salford': 'salfordcitycouncil.my.site.com'}


def rows():
    raw = Path(__file__).with_name('arcus-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('ARCUS_MANIFEST_DIGEST')
    data = json.loads(raw)
    result = data['rows']
    if (len(result) != 57 or len({r['application_id'] for r in result}) != 57
            or {r['application_id'] for r in data['manual_candidates']} != {1100}):
        raise ValueError('ARCUS_MANIFEST_SCOPE')
    for row in result:
        u = urlsplit(row['source_url'])
        if (row['application_id'] == 1100 or row['council'] not in ORIGINS
                or u.scheme != 'https' or u.netloc != ORIGINS[row['council']]
                or u.path != '/pr/s/detail/' + row['source_identifier'] or u.fragment
                or parse_qs(u.query) != {'c__r': ['Arcus_BE_Public_Register']}
                or not re.fullmatch('[A-Za-z0-9]{18}', row['source_identifier'])):
            raise ValueError('ARCUS_MANIFEST_DESTINATION')
    return result


def admitted_row(application_id):
    matched = [row for row in rows() if row['application_id'] == application_id]
    if len(matched) != 1:
        raise ValueError('ARCUS_UNADMITTED_IDENTITY')
    return matched[0]


def case_definitions():
    return {'arcus_' + str(r['application_id']):
            (r['application_id'], r['reference'], r['source_url']) for r in rows()}
