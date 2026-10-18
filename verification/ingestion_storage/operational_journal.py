"""The one-use audit journal, separated so single-purpose controllers can use it without importing the capture/screening runner."""
import hashlib,json,os
from pathlib import Path
from .operational_publication import canonical,Uncertain


class Journal:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        self.file=self.root/'events.jsonl';self.sequence=0;self.head='0'*64
        self.file.touch(mode=0o600,exist_ok=False)
        self.sync_dir()
    def sync_dir(self):
        for p in (self.root,self.root.parent):
            fd=os.open(p,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    def emit(self,event,payload):
        record=dict(sequence=self.sequence,event=event,payload=payload,previous_sha256=self.head)
        head=hashlib.sha256(canonical(record)).hexdigest();raw=canonical(dict(record,sha256=head))+b'\n'
        if self.file.stat().st_size+len(raw)>1024**2:raise Uncertain('AUDIT_BOUND')
        with self.file.open('ab') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        self.sequence+=1;self.head=head
    def save(self,name,value):
        if name not in {'progress.json','final-result.json'}:raise ValueError('CHECKPOINT_PATH')
        raw=canonical(value)
        if len(raw)>256*1024:raise ValueError('CHECKPOINT_BOUND')
        persisted=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        if persisted+len(raw)>2*1024**2-8192:raise ValueError('CHECKPOINT_COMBINED_OUTPUT_RESERVE')
        temp=self.root/(name+'.next')
        with temp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        temp.replace(self.root/name);self.sync_dir()
        if (self.root/name).read_bytes()!=raw:raise Uncertain('CHECKPOINT_READBACK')

    def progress(self):
        from app.ingestion.ledger import digest
        state=json.loads((self.root/'progress.json').read_bytes());previous='0'*64;sealed=None
        for i,line in enumerate(self.file.read_bytes().splitlines()):
            event=json.loads(line);sha=event.pop('sha256')
            if event['sequence']!=i or event['previous_sha256']!=previous or hashlib.sha256(canonical(event)).hexdigest()!=sha:raise Uncertain('AUDIT_CHAIN_BINDING')
            previous=sha
            if event['event']=='progress_saved':sealed=event['payload']['sha256']
        if previous!=self.head or digest(state)!=sealed:raise Uncertain('DURABLE_PROGRESS_SEAL')
        return state
