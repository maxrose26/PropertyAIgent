"""Closed, separately authorised subset of the accepted Arcus manifest."""
import hashlib
import json
from pathlib import Path
from . import batch
from .arcus_manifest import admitted_row

MANIFEST_SHA256 = 'c455f6448a689840d6037781ee935fe1ef4a0be0cae06d0e6d47b65d1cc7ef1c'
IDENTITIES = ((534, 'PA/2024/1313'), (540, 'PA/2024/1538'), (545, 'PA/2024/1621'), (547, 'PA/2024/1622'), (554, 'PA/2025/0043'), (566, '23/81719/HYBEIA'), (1146, '23/81238/OUTEIA'), (1149, '23/81742/HYBEIA'), (1155, '23/82436/FUL'), (1156, '23/81788/FUL'), (1159, 'PA/2023/0425'), (1165, 'PA/2023/0550'), (1167, 'PA/2023/0532'), (1177, 'PA/2023/0556'), (1181, '20/76664/OUT'))
CONTEXTS = {name: batch.ManifestSpec(name, MANIFEST_SHA256, count, True, 'ARCUS')
            for name, count in [('salford15_a', 6), ('salford15_b', 9)]}

def manifest(spec):
    if spec not in CONTEXTS.values(): raise ValueError('SALFORD15_SCOPE')
    raw = Path(__file__).with_name('salford15-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256: raise ValueError('SALFORD15_DIGEST')
    data = json.loads(raw)
    if (set(data) != {'schema','accepted_merge','prior_run','quarantined','rows'}
        or data['schema'] != 1 or data['accepted_merge'] != '898c0c93889aa9df8fa5454818cf45de0a920d25'
        or data['prior_run'] != '38475718624' or data['quarantined'] != [266]):
        raise ValueError('SALFORD15_AUTHORITY')
    rows = data['rows']
    if tuple((r['application_id'],r['reference']) for r in rows) != IDENTITIES:
        raise ValueError('SALFORD15_IDENTITIES')
    if any(r != admitted_row(r['application_id']) or r['council'] != 'salford' for r in rows):
        raise ValueError('SALFORD15_DESTINATION')
    chosen = rows[:6] if spec.filename == 'salford15_a' else rows[6:]
    if len(chosen) != spec.count: raise ValueError('SALFORD15_COUNT')
    return [{'identity':r,'policy':'A','selection_stratum':'retained_policy_due'} for r in chosen]
