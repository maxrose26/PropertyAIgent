"""Finite owner-authenticated Git evidence publisher. No runtime credentials.

Every write is intent-journalled. An uncertain response is never retried. The
fast-forward-only ref update prevents overwriting a concurrent publication.
"""
import base64,hashlib,json,re,subprocess,time

REPO='repos/maxrose26/PropertyAIgent'
BRANCH='stage4/narrow-continuation-evidence-20261016'

class Uncertain(RuntimeError):
    pass


def blob_bytes(blob):
    """The decoded bytes of a contents/blob response, accepted ONLY if the response's git blob identity matches them (the contract the publisher's own readback relies on; no other field is trusted)."""
    try:
        raw=base64.b64decode(blob['content']);identity=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if blob['sha']==identity:return raw
    except Exception:pass
    raise Uncertain('PUBLICATION_BLOB_IDENTITY')

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()

class GitHub:
    def __init__(self,emit,check,*,runner=subprocess.run,bound=40):
        self.emit=emit;self.check=check;self.runner=runner;self.requests=0;self.mutation_uncertain=False;self.bound=bound

    def call(self,method,path,body=None):
        self.check()
        if method!='GET' and self.mutation_uncertain:raise Uncertain('PRIOR_GITHUB_MUTATION_UNCERTAIN')
        if self.requests>=self.bound:raise ValueError('GITHUB_REQUEST_BOUND')
        self.requests+=1
        self.emit('github_intent',dict(method=method,path=path,ordinal=self.requests))
        command=['gh','api','--method',method,path]
        if method=='DELETE':command+=['--include','--silent']
        if body is not None:command+=['--input','-']
        try:
            r=self.runner(command,input=canonical(body) if body is not None else None,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            if r.returncode or len(r.stdout)+len(r.stderr)>3*1024**2:raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')
            if method=='DELETE':
                if re.findall(rb'^HTTP/\S+\s+(\d{3})(?:\s|$)',r.stdout,re.M)!=[b'204']:raise Uncertain('DELETE_ACK_UNCERTAIN')
                value=None
            else:value=json.loads(r.stdout) if r.stdout else None
        except BaseException:
            if method!='GET':self.mutation_uncertain=True
            raise Uncertain('GITHUB_RESPONSE_UNCERTAIN') from None
        self.emit('github_ack',dict(method=method,path=path,ordinal=self.requests))
        self.check();return value

    NOT_FOUND=re.compile(rb'\(HTTP 404\)\s*$')

    NOT_FOUND=re.compile(rb'\(HTTP 404\)\s*$')

    def probe(self,path):
        """A read-only GET whose confirmed HTTP 404 (gh's final line `... (HTTP 404)`) means 'not there (yet)' and returns None. Every other failure - another status, a message that merely mentions 404, an
        empty successful answer, an unreadable or oversized one - is Uncertain, exactly as for call(). The audit records what was answered (PRESENT / ABSENT_HTTP_404)."""
        self.check()
        if self.requests>=self.bound:raise ValueError('GITHUB_REQUEST_BOUND')
        self.requests+=1
        self.emit('github_intent',dict(method='GET',path=path,ordinal=self.requests))
        try:
            r=self.runner(['gh','api','--method','GET',path],input=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            if len(r.stdout)+len(r.stderr)>3*1024**2:raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')
            if r.returncode:
                if not self.NOT_FOUND.search(r.stderr.rstrip()):raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')
                value=None
            else:
                if not r.stdout:raise Uncertain('GITHUB_RESPONSE_UNCERTAIN')      # a successful probe that returns nothing is not evidence of absence
                value=json.loads(r.stdout)
        except BaseException:raise Uncertain('GITHUB_RESPONSE_UNCERTAIN') from None
        self.emit('github_ack',dict(method='GET',path=path,ordinal=self.requests,result='PRESENT' if value is not None else 'ABSENT_HTTP_404'))
        self.check();return value

    def names(self):
        data=self.call('GET',REPO+'/environments/stage4-production-canary/secrets?per_page=100')
        if not isinstance(data,dict) or type(data.get('total_count')) is not int or not 0<=data['total_count']<=100 or not isinstance(data.get('secrets'),list):raise Uncertain('SECRET_NAMES_BOUND')
        names=[x['name'] for x in data['secrets']]
        if any(not isinstance(n,str) for n in names) or len(names)!=data['total_count'] or len(set(names))!=len(names):raise Uncertain('SECRET_NAMES_SHAPE_OR_INCOMPLETE_PAGE')
        return names

    def put_secret(self,name,value):
        if name not in {'INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL'}:raise ValueError('EXACT_SECRET_NAME')
        self.check()
        if self.mutation_uncertain:raise Uncertain('PRIOR_GITHUB_MUTATION_UNCERTAIN')
        if self.requests>=40:raise ValueError('GITHUB_REQUEST_BOUND')
        self.requests+=1;self.emit('secret_mapping_intent',dict(name=name,ordinal=self.requests))
        try:
            r=self.runner(['gh','secret','set',name,'--repo','github.com/maxrose26/PropertyAIgent','--env','stage4-production-canary'],input=value.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
            if r.returncode or len(r.stdout)+len(r.stderr)>8192:raise Uncertain('SECRET_MAPPING_UNCERTAIN')
        except BaseException:
            self.mutation_uncertain=True
            raise Uncertain('SECRET_MAPPING_UNCERTAIN') from None
        self.emit('secret_mapping_ack',dict(name=name));self.check()

    def publish(self,files,*,directory,expected_head):
        if not directory.startswith('docs/design/ingestion-operational-execution-') or '..' in directory.split('/') or len(files)>8:raise ValueError('PUBLICATION_PATH')
        if sum(len(b) for b in files.values())>2*1024**2:raise ValueError('PUBLICATION_BYTES')
        ref=REPO+'/git/refs/heads/'+BRANCH
        readref=REPO+'/git/ref/heads/'+BRANCH
        current=self.call('GET',readref)
        if current['object']['sha']!=expected_head:raise Uncertain('EVIDENCE_HEAD_MOVED_RECONCILE')
        commit=self.call('GET',REPO+'/git/commits/'+expected_head);elements=[]
        for name,raw in files.items():
            if '/' in name or not isinstance(raw,bytes):raise ValueError('PUBLICATION_FILE')
            blob=self.call('POST',REPO+'/git/blobs',dict(content=base64.b64encode(raw).decode(),encoding='base64'))
            expected=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if blob['sha']!=expected:raise Uncertain('BLOB_IDENTITY')
            elements.append(dict(path=directory+'/'+name,mode='100644',type='blob',sha=expected))
        tree=self.call('POST',REPO+'/git/trees',dict(base_tree=commit['tree']['sha'],tree=elements))
        new=self.call('POST',REPO+'/git/commits',dict(message='Preserve finite operational evidence [skip render]',tree=tree['sha'],parents=[expected_head]))
        # A competing descendant makes our commit divergent; force=false must
        # reject it. No force update or fallback publication branch is allowed.
        self.call('PATCH',ref,dict(sha=new['sha'],force=False))
        observed=self.call('GET',readref)
        if observed['object']['sha']!=new['sha']:raise Uncertain('PUBLICATION_HEAD_READBACK')
        for entry in elements:
            # Read the path AT the committed revision. Reading an orphan blob
            # by hash alone would not establish its membership in that commit.
            blob=self.call('GET',REPO+'/contents/'+entry['path']+'?ref='+new['sha'])
            raw=base64.b64decode(blob['content'])
            if blob['sha']!=entry['sha'] or raw!=files[entry['path'].split('/')[-1]]:raise Uncertain('PUBLICATION_BYTES_READBACK')
        self.emit('publication_verified',dict(commit=new['sha'],files={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}))
        return new['sha']
