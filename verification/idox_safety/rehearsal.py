"""Offline-only fixed fixture worker and independent parent deadline rehearsal.

No live mode. No council request. Parent owns one subprocess; no descendants are
started by this worker. This is not hostile-process containment. A future hosted
runner's disposal remains the final process boundary, subject to later review.
"""
import json
import os
import selectors
import socket
import subprocess
import sys
import time
from xml.etree import ElementTree as ET
from verification.idox_safety.collector import CONFIGS, VERSION, Exchange, Failure, FixtureTape, collect, encode_result


def deny_network(*args, **kwargs):
    raise RuntimeError("offline network denied")


def install_network_denial():
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network


def page(number=1, total=1, entries=None, terminal=True, zero=False, next_page=None):
    """Synthetic structural expectations, not retained council markup."""
    root = ET.Element("fixture-results", version=VERSION, page=str(number), total=str(total),
                      terminal=str(terminal).lower(), zero=str(zero).lower())
    for reference, link in (entries if entries is not None else [("SYNTH/001", "applicationDetails.do?activeTab=summary&keyVal=SYNTH1")]):
        ET.SubElement(root, "candidate", reference=reference, href=link)
    if next_page is not None:
        ET.SubElement(root, "next", page=str(next_page))
    return ET.tostring(root)


def tape(body=None):
    return FixtureTape([Exchange("FORM", (b"OFFLINE_FORM_V1",)), Exchange("SUBMIT", (body or page(),))])


def worker(scenario):
    install_network_denial()
    if scenario == "hung":
        while True:
            time.sleep(60)
    if scenario == "exception":
        raise RuntimeError("synthetic exception")
    if scenario == "overflow":
        os.write(1, b"X" * 100_000)
        return
    if scenario not in CONFIGS:
        raise ValueError("unknown offline scenario")
    result = collect(scenario, "2026-10-01", "2026-10-01", CONFIGS[scenario].basis, tape())
    os.write(1, encode_result(result))


def supervise(scenario, deadline=30):
    if scenario not in {*CONFIGS, "hung", "exception", "overflow"} or not 0 < deadline <= 30:
        raise ValueError("fixed offline scenario/deadline required")
    started, output = time.monotonic(), bytearray()
    outcome, process = "PARTIAL_RETRIEVAL", None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen([sys.executable, "-m", "verification.idox_safety.rehearsal", "--worker", scenario],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - (time.monotonic()-started)
            if remaining <= 0:
                outcome = "TIMEOUT"
                break
            for key, _ in selector.select(min(remaining, 0.05)):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > 65_536:
                    outcome = "BUDGET_EXCEEDED"
                    break
            if outcome == "BUDGET_EXCEEDED":
                break
        if outcome not in {"TIMEOUT", "BUDGET_EXCEEDED"}:
            try:
                process.wait(timeout=max(0.001, deadline-(time.monotonic()-started)))
            except subprocess.TimeoutExpired:
                outcome = "TIMEOUT"
            else:
                outcome = "COMPLETE" if process.returncode == 0 else "PARTIAL_RETRIEVAL"
        if outcome == "COMPLETE":
            try:
                from verification.idox_safety.collector import validate_result
                parsed = validate_result(json.loads(output))
                outcome = parsed["completion_state"]
            except (Failure, ValueError, TypeError, KeyError):
                outcome = "PARTIAL_RETRIEVAL"
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            process.stdout.close()
        selector.close()
    if outcome != "COMPLETE":
        output.clear()
    return {"mode": "SYNTHETIC_OFFLINE", "outcome": outcome, "cleanup_verified": process is not None and process.poll() is not None,
            "worker_returncode": process.returncode if process else None, "elapsed_seconds": round(time.monotonic()-started, 6),
            "artifact": json.loads(output) if output else None}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
    else:
        raise SystemExit("offline test worker only; no live launcher")
