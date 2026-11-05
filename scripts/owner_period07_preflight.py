"""Fixed read-only child; invoked only by the authenticated hosted adapter."""
import json
from verification.ingestion_storage import owner_pilot as pilot
from verification.ingestion_storage.period07_readonly import run

def main():
    try:
        with pilot.envelope():result=run()
    except BaseException:
        result={'version':'PERIOD07_READONLY_PREFLIGHT_V1','status':'REFUSED','reason':'PREFLIGHT_ENVELOPE_OR_CONFIGURATION','database_writes':0,'journal_writes':0,'provider_mutations':0,'job_submissions':0}
    print(json.dumps(result,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
