"""One finite real P0-A supervisor process, invoked only by isolated tests."""
import json
import os
from pathlib import Path
import sys
import time
from sqlalchemy.orm import Session
from app.db.ah_disposable_postgres import create_disposable_engine
from app.pipeline.discovery_owner import DiscoveryOwner, reconcile_owners
from app.pipeline.discovery_watchdog import DiscoveryWatchdog
from scripts.run_daily_councils import run_one_council

path=Path(sys.argv[1]);spec=json.loads(path.read_text())
engine=create_disposable_engine(spec['proof'])
os.environ['PROPERTYAIGENT_MIXED_RECORDING']=str(path)
with DiscoveryWatchdog(time.monotonic()+90) as watchdog, DiscoveryOwner(str(path.parent/'owner.lock')) as owner:
    owner.watchdog=watchdog
    owner.limits={'invocation_seconds':90}
    with Session(engine,expire_on_commit=False) as session:
        reconcile_owners(session,owner)
        run=run_one_council(session,spec['council'],timeout_seconds=60,
                            triggered_by='manual',include_ai_stages=False,owner=owner)
        (path.parent/(path.stem+'-run.json')).write_text(json.dumps(dict(id=run.id,status=run.status,progress=json.loads(run.progress))))
engine.dispose()
