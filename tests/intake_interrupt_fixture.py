"""Disposable subprocess harness; real SIGKILL is sent by the parent test.

No hooks in the production command. Runtime's exact disposable URL/period
validation remains mandatory. No source/network production route is invoked.
"""
import argparse,json,time
from contextlib import contextmanager
from pathlib import Path
from verification.ingestion_storage.daily_intake_runtime import Runtime


def main():
    parser=argparse.ArgumentParser()
    for key in ('period','output','disposable-sources','disposable-archive','fault','ready'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();args.hostaddr=None;args.after=None;args.page_size=3;args.backlog=False
    fired=False
    def pause(where):
        nonlocal fired
        if where==args.fault and not fired:
            fired=True;Path(args.ready).write_text(where)
            while True:time.sleep(.05)
    class Interrupted(Runtime):
        def issue(self,reg):
            if reg.kind=='SCREENING':pause('capture')
            result=super().issue(reg)
            if reg.kind=='CAPTURE':pause('registration')
            else:pause('screening')
            return result
        def collect(self,row):
            pause('source_intent');return super().collect(row)
        def archive(self,raw):
            result=super().archive(raw);pause('archive');return result
        @contextmanager
        def connection(self,*a,**kw):
            operation=None
            with super().connection(*a,**kw) as (c,budget):
                class Proxy:
                    def __getattr__(self,name):return getattr(c,name)
                    def execute(self,statement,params=None,*a,**kw):
                        nonlocal operation
                        if params and 'p' in params:
                            operation=json.loads(params['p']).get('operation')
                        return c.execute(statement,params,*a,**kw)
                yield Proxy(),budget
            if operation=='intake_close':pause('closure')
            if operation=='intake_finish':pause('finish_ack')
    original=Path.write_bytes
    def write(path,data):
        result=original(path,data)
        if path.name.endswith('-final.json'):pause('publication')
        return result
    runtime=Interrupted(args)
    if not runtime.test:raise RuntimeError('DISPOSABLE_ONLY')
    Path.write_bytes=write
    result=runtime.execute()
    print(json.dumps(result))

if __name__=='__main__':main()
