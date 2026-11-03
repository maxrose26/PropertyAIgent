"""Fixed trusted-OS adapter to the existing restricted daily command, no admin I/O."""
import argparse,json,os,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--hostaddr',required=True);p.add_argument('--period',choices=('b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02'),default='b-dbpilot-20261027-1102-01');a=p.parse_args()
    import ipaddress
    if ipaddress.ip_address(a.hostaddr).version!=4:raise SystemExit(2)
    PERIOD=a.period
    allowed={'PATH','HOME','LANG','TZ','PYTHONUNBUFFERED','PLAYWRIGHT_BROWSERS_PATH','INGESTION_RENDER_PROFILE',
             'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','RENDER_SERVICE_ID','RENDER_GIT_COMMIT'}
    env={k:v for k,v in os.environ.items() if k in allowed}
    if set(env)&{'DATABASE_URL','PROPERTYAIGENT_INTAKE_RENDER_API_KEY','GH_TOKEN'}:raise SystemExit(2)
    env.update(PROPERTYAIGENT_COMMAND_IDENTITY='database-pilot-daily',PROPERTYAIGENT_ACCESS_POLICY=str(Path('docs/design/database-pilot-20261103/command-policy.json').resolve()),PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear();os.environ.update(env)
    sys.argv=['scripts.run_daily_councils','--period',PERIOD,'--output','/tmp/propertyaigent-'+PERIOD,'--hostaddr',a.hostaddr]
    from scripts.run_daily_councils import main as daily
    return daily()

if __name__=='__main__':raise SystemExit(main())
