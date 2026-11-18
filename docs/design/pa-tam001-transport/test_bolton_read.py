import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from psycopg.pq import TransactionStatus
from psycopg import ConnectionInfo

spec=importlib.util.spec_from_file_location('bounded',Path(__file__).with_name('bolton-read.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Connection:
    def __init__(self, failure=None, ack=True, close_error=False, payload='[]'):
        self.calls=[];self.closed=False;self.failure=failure;self.close_error=close_error;self.payload=payload
        self.info=ConnectionInfo(SimpleNamespace(transaction_status=int(TransactionStatus.IDLE if ack else TransactionStatus.UNKNOWN)))
    def execute(self,sql):
        self.calls.append(sql)
        if len(self.calls)==self.failure: raise RuntimeError('fixture')
        return SimpleNamespace(statusmessage='ROLLBACK' if sql=='ROLLBACK' else 'OK',fetchone=lambda:(self.payload,))
    def close(self):
        if self.close_error:raise RuntimeError('close')
        self.closed=True
class DB:
    def __init__(self,c):self.c=c;self.opens=0
    @contextmanager
    def connection(self):
        self.opens+=1
        yield self.c
class Checks(unittest.TestCase):
    def invoke(self,c,age=0):
        d=DB(c);r=m.run(lambda:d,time.monotonic()-age)
        self.assertLessEqual(d.opens,1);self.assertLessEqual(len(c.calls),7)
        return r
    def test_exact_statements(self):
        sql=Path(__file__).with_name('bolton-read.sql').read_text()
        source='\n'.join(l for l in sql.splitlines() if not l.startswith('--'))
        self.assertEqual(m.STATEMENTS,[s.strip() for s in source.split(';') if s.strip()])
        c=Connection();r=self.invoke(c)
        self.assertEqual(len(c.calls),7);self.assertEqual(c.calls[:3],m.STATEMENTS[:3]);self.assertEqual(c.calls[-1],'ROLLBACK')
        for i in range(3):self.assertIn(m.STATEMENTS[i+3],c.calls[i+3])
        self.assertTrue(r['rollback_acknowledged']);self.assertTrue(r['connection_closed'])
    def test_unknown_ack(self):
        r=self.invoke(Connection(ack=False));self.assertFalse(r['rollback_acknowledged']);self.assertTrue(r['connection_closed'])
    def test_close_failure(self):
        r=self.invoke(Connection(close_error=True));self.assertTrue(r['rollback_acknowledged']);self.assertFalse(r['connection_closed'])
    def test_failed_select(self):
        c=Connection(failure=4);r=self.invoke(c);self.assertEqual(len(c.calls),5);self.assertTrue(r['rollback_acknowledged']);self.assertTrue(c.closed)
    def test_lost_rollback_ack(self):
        c=Connection(failure=7);r=self.invoke(c);self.assertFalse(r['rollback_acknowledged']);self.assertTrue(c.closed)
    def test_server_cap(self):
        c=Connection(payload='null');r=self.invoke(c);self.assertEqual(r['reason'],'SERVER_RESULT_CAP');self.assertTrue(c.closed)
    def test_cumulative_cap(self):
        c=Connection(payload=json.dumps(['x'*22000]));r=self.invoke(c);self.assertEqual(r['reason'],'RESULT_CAP');self.assertTrue(c.closed)
    def test_expired_deadline(self):
        c=Connection();r=self.invoke(c,16);self.assertEqual(r['connections_attempted'],0);self.assertEqual(c.calls,[])
if __name__=='__main__':unittest.main()
