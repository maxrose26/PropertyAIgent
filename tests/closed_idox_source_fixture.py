"""Synthetic transport inside the real private detail worker; no council contact."""
import sys
from pathlib import Path
from unittest.mock import patch
from verification.ingestion_storage.operational_source import main
from verification.direct_reference.fixtures import Session

def run():
    i=sys.argv.index('--fixture-html');body=Path(sys.argv[i+1]).read_bytes();del sys.argv[i:i+2]
    with patch('verification.direct_reference.refresh.requests_session',lambda:Session(body)):
        main()

if __name__=='__main__':run()
