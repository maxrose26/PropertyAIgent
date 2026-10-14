"""Measure a paused normal browser POST; never send/reconstruct an RPC."""
from urllib.parse import urlsplit
from .arcus_ui_window import AURA
MAX_BYTES=20*1024*1024


def combined_bytes(audit):
    return max(audit.get('decoded_bytes',0),audit.get('encoded_bytes',0))+audit.get('outbound_payload_bytes',0)


async def measure_post(event,client,audit,expected_aura=AURA):
    request=event['request'];u=urlsplit(request['url'])
    if request['method']!='POST' or u._replace(query='').geturl()!=expected_aura:
        return 'POST_DESTINATION'
    headers={k.lower():v for k,v in request.get('headers',{}).items()}
    if headers.get('content-encoding','identity').strip().lower()!='identity':return 'POST_CONTENT_ENCODING'
    content_type=headers.get('content-type','').split(';',1)[0].strip().lower()
    if content_type!='application/x-www-form-urlencoded':return 'POST_MEDIA_TYPE'
    body=request.get('postData')
    if body is None:
        network_id=event.get('networkId')
        if not isinstance(network_id,str) or not network_id:return 'POST_BODY_UNAVAILABLE'
        try:
            # Browser-local protocol inspection, not another council request.
            data=await client.send('Network.getRequestPostData',{'requestId':network_id})
            body=data.get('postData')
            audit['post_body_cdp_reads']=audit.get('post_body_cdp_reads',0)+1
        except Exception:return 'POST_BODY_UNAVAILABLE'
    if not isinstance(body,str):return 'POST_BODY_UNAVAILABLE'
    size=len(body.encode('utf-8'))
    if not size:return 'POST_BODY_EMPTY'
    declared=headers.get('content-length')
    if declared is not None and (not str(declared).isdigit() or int(declared)!=size):
        return 'POST_BODY_LENGTH_MISMATCH'
    audit['largest_observed_post_bytes']=max(audit.get('largest_observed_post_bytes',0),size)
    if size>MAX_BYTES or combined_bytes(audit)+size>MAX_BYTES:return 'POST_AGGREGATE_BYTE_LIMIT'
    audit['outbound_payload_bytes']=audit.get('outbound_payload_bytes',0)+size
    audit['measured_public_ui_posts']=audit.get('measured_public_ui_posts',0)+1
    return None
