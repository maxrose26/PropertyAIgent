"""Shared transport accounting: wire/decoded overlap is counted once."""
def combined_bytes(audit):
    return max(audit.get('decoded_bytes',0),audit.get('encoded_bytes',0))+audit.get('outbound_payload_bytes',0)
