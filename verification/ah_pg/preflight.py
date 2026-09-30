"""Dependency/version inventory; runs before cluster initialization."""
import importlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

out=Path(sys.argv[1])
report={'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'dependencies':{},'errors':[]}
for line in Path(__file__).with_name('requirements.lock').read_text().splitlines():
    name,wanted=line.split('==')
    try:
        actual=version(name); report['dependencies'][name]=actual
        if actual!=wanted: report['errors'].append(name+': pinned version mismatch')
    except Exception as e: report['errors'].append(name+': '+str(e))
for name in ('psycopg','sqlalchemy','pytest','pandas','streamlit','playwright','openai','pdfplumber','docx','yaml','rapidfuzz'):
    try: importlib.import_module(name)
    except Exception as e: report['errors'].append(name+': '+str(e))
try:
    import psycopg
    report['driver']='psycopg3 (project driver; psycopg2 is not used)'
    report['libpq']=psycopg.pq.version(); report['pq_implementation']=psycopg.pq.__impl__
except Exception: pass
out.write_text(json.dumps(report,indent=2)+'\n')
if report['errors']: raise SystemExit('\n'.join(report['errors']))
