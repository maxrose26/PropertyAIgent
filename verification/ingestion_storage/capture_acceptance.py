"""The restricted GitHub-hosted half of the Bolton CAPTURE ACCEPTANCE (specification 032 section 13). It is the accepted stable pipeline - connection qualification, the checkout binding, ONE form GET that
must be a valid form before any listing request, the listing collection, durable retention before the checkpoint, source-free screening, publication-then-closure - differing ONLY in the identity it
runs under: its own authority name (so its own named allowances), its own evidence directory and its own registered manifest. Nothing here can register an authority, hold an administrative credential or
change a credential."""
from . import stable_pipeline as sp
from .operational_runner import CAPTURE_AUTHORITY,CAPTURE_EVIDENCE_DIRECTORY,CAPTURE_HOSTED_AUTHORITY

CAPTURE_MANIFEST_PATH='docs/design/ingestion-capture-acceptance-20261022/MANIFEST.json'


class CaptureHostedRunner(sp.HostedRunner):
    EVIDENCE=CAPTURE_EVIDENCE_DIRECTORY
    AUTHORITY=CAPTURE_AUTHORITY
    MODE_NAME='BOLTON_CAPTURE_ACCEPTANCE_HOSTED'
    MANIFEST=CAPTURE_MANIFEST_PATH


def main(argv=None):
    return sp.main(argv,authority=CAPTURE_HOSTED_AUTHORITY,runner_class=CaptureHostedRunner,manifest_path=CAPTURE_MANIFEST_PATH)


if __name__=='__main__':main()
