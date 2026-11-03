import json
from app.owner_intake import configuration_readback, SERVICE

class Reply:
    def __init__(self,status=200,body=None):self.status_code=status;self.body=body or {'id':SERVICE,'suspended':'suspended','autoDeploy':'no'}
    def __enter__(self):return self
    def __exit__(self,*x):pass
    def iter_content(self,n):yield json.dumps(self.body).encode()
class Transport:
    def __init__(self,reply):self.reply=reply;self.calls=[];self.closed=False
    def get(self,*a,**k):self.calls.append((a,k));return self.reply
    def close(self):self.closed=True

def test_missing_postgres_never_opens_sqlite_and_key_only_inside_transport():
    s=Transport(Reply());v=configuration_readback({'PROPERTYAIGENT_INTAKE_RENDER_API_KEY':'SECRET_SENTINEL'},session=s)
    assert v['database_status']=='CONFIGURED_POSTGRES_REQUIRED' and v['render_status']=='EXACT_SERVICE_READ_VERIFIED'
    assert v['requests']==1 and v['provider_mutations']==v['database_mutations']==0 and s.closed
    assert 'SECRET_SENTINEL' not in json.dumps(v) and s.calls[0][1]['allow_redirects'] is False
    assert s.calls[0][0]==('https://api.render.com/v1/services/'+SERVICE,)

def test_http_refusal_and_overflow_suppress_values():
    for reply,status in [(Reply(403),'HTTP_REFUSED'),(Reply(body={'id':SERVICE,'secret':'x'*40000}),'READBACK_UNCERTAIN')]:
        s=Transport(reply);v=configuration_readback({'PROPERTYAIGENT_INTAKE_RENDER_API_KEY':'SECRET_SENTINEL'},session=s)
        assert v['render_status']==status and len(json.dumps(v))<2048 and 'SECRET_SENTINEL' not in json.dumps(v) and s.closed

def test_database_server_identity_read_only_and_connection_closed():
    class C:
        closed=False
        def __enter__(self):return self
        def __exit__(self,*x):self.closed=True
        def execute(self,sql):
            queries.append(sql);self.sql=sql;return self
        def fetchone(self):
            return (False,) if 'to_regclass' in self.sql else ('postgres','postgres',False,True,True,True,True)
    queries=[];seen={};c=C()
    def connect(**kw):seen.update(kw);return c
    v=configuration_readback({'DATABASE_URL':'postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRET_SENTINEL@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'},connect=connect)
    assert queries[0]=='BEGIN READ ONLY' and queries[-1]=='ROLLBACK' and len(queries)==4
    assert v['database_status']=='SERVER_IDENTITY_VERIFIED' and v['database_closed'] and v['session_mode_owner_route']
    assert seen['password']=='SECRET_SENTINEL' and seen['sslmode']=='verify-full' and 'SECRET_SENTINEL' not in json.dumps(v)
