"""Native Streamlit ASGI boundary; no replacement authentication endpoints."""
from http.cookies import SimpleCookie
from app.security.access import AccessDenied, registry


class AccessMiddleware:
    def __init__(self, app):
        self.app = app
        registry.middleware_ready = True

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            path = scope.get('path', '')
            # No application payload may use native unauthorised media storage.
            if path.startswith('/media/') or path.startswith('/app/static/'):
                if scope['type'] == 'http':
                    await send({'type': 'http.response.start', 'status': 404, 'headers': []})
                    await send({'type': 'http.response.body', 'body': b''})
                else:
                    await send({'type': 'websocket.close', 'code': 1008})
                return
            if path == '/auth/logout':
                cookies = SimpleCookie()
                for key, value in scope.get('headers', []):
                    if key.lower() == b'cookie':
                        cookies.load(value.decode('latin1'))
                try:
                    registry.revoke_native({k: v.value for k, v in cookies.items()})
                except AccessDenied:
                    pass  # Native logout still clears malformed/missing cookies.
        await self.app(scope, receive, send)
