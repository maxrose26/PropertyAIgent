"""Deliver authorised bytes only through the current Streamlit connection.

There is no HTTP file registration, shared cache or server media URL. A file
already saved by an authorised user cannot be revoked.
"""
import base64
import hashlib
from pathlib import Path
import re
import streamlit as st
from app.security.access import require_admitted

_DELIVER = st.components.v2.component('propertyaigent_delivery', js='''
export default function({data, parentElement}) {
  const bytes = Uint8Array.from(atob(data.payload), c => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], {type: data.mime}));
  const node = document.createElement(data.image ? 'img' : 'a');
  if (data.image) { node.src=url; node.alt='Source evidence'; node.style.maxWidth='100%'; node.width=data.width; }
  else { node.href=url; node.download=data.filename; node.textContent='Save '+data.filename; }
  parentElement.replaceChildren(node);
  return () => { URL.revokeObjectURL(url); node.remove(); };
}
''')
_MIMES = {'text/csv', 'application/pdf', 'image/png', 'image/jpeg', 'image/webp'}


def _payload(data, mime, filename, *, image=False, width=320, key=None):
    actor = require_admitted()
    if mime not in _MIMES:
        raise ValueError('Unsupported delivery format')
    raw = data.encode('utf-8') if isinstance(data, str) else bytes(data)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('Delivery exceeds the 32 MB pilot limit')
    name = re.sub(r'[^A-Za-z0-9_. -]', '_', str(filename))[:120]
    require_admitted()
    _DELIVER(data=dict(payload=base64.b64encode(raw).decode('ascii'), mime=mime, filename=name, image=image, width=width), key='delivery-'+actor.lease_id+'-'+str(key or hashlib.sha256(raw).hexdigest()))


def download_button(label, data, file_name=None, mime=None, key=None, **kwargs):
    actor=require_admitted()
    raw=data.encode('utf-8') if isinstance(data,str) else bytes(data)
    request_key='_delivery_request_'+str(key or label)
    scope=(actor.lease_id,actor.revision,st.session_state.get('active_buyer_key'),hashlib.sha256(raw).hexdigest())
    clicked = st.button(label, key=key, disabled=kwargs.get('disabled',False), help=kwargs.get('help'))
    if clicked:
        st.session_state[request_key]=scope
    # A component mount may itself rerun the page. Retain only the request's
    # scope/digest, never cached bytes. Every render uses freshly authorised
    # data and loses delivery immediately when its scope or content changes.
    if st.session_state.get(request_key)==scope and not kwargs.get('disabled',False):
        _payload(data, mime or 'text/csv', file_name or 'download.csv', key=key)
    return clicked


def image(path, width=320):
    require_admitted()
    from app.db.session import DATA_DIR
    source = Path(path).resolve()
    if not source.is_relative_to(DATA_DIR.resolve()):
        raise ValueError('Evidence image outside data directory')
    # Decode/re-encode to a safe raster; never send SVG/HTML from a source file.
    import io
    from PIL import Image
    with Image.open(source) as raster:
        raster.thumbnail((1600,1600))
        output=io.BytesIO(); raster.convert('RGB').save(output, format='JPEG')
    _payload(output.getvalue(), 'image/jpeg', 'evidence.jpg', image=True, width=width)
