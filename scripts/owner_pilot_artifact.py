"""Build receipt for the existing browser/daily command; never contacts a source."""
import hashlib,importlib.metadata,json,os
from pathlib import Path

def main():
    import playwright
    from playwright.sync_api import sync_playwright
    from verification.direct_reference.prepared_font_cache import headless_shell_executable
    from verification.ingestion_storage.daily_intake_runtime import execution_binding
    directory=(Path(playwright.__file__).parent/'driver/package/.local-browsers').resolve()
    executable=headless_shell_executable(str(directory)).resolve()
    with executable.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(executable),headless=True)
        version=browser.version;browser.close()
    v=dict(kind='DATABASE_PILOT_BUILD_NOT_EXECUTION',execution_binding=execution_binding(),browser_path=str(directory),
           browser_executable=str(executable),browser_sha256=sha,browser_version=version,browser_canary='LAUNCHED_AND_CLOSED',
           dependency_versions={k:importlib.metadata.version(k) for k in ('playwright','psycopg','SQLAlchemy','requests','cryptography','psutil')})
    root=Path('.b-build');root.mkdir(exist_ok=True)
    raw=json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    (root/'database-pilot-artifact.json').write_bytes(raw)
    print('DATABASE_PILOT_BUILD_RECEIPT '+raw.decode(),flush=True)

if __name__=='__main__':main()
