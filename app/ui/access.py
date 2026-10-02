"""Native identity adapter, called before every page's data boundary."""
from contextlib import contextmanager
from urllib.parse import urlsplit
import streamlit as st
from app.security.access import AccessDenied, AccessUnavailable, actor_scope, load_policy, registry


def clear_view_state():
    for key in list(st.session_state):
        if key != '_access_lease':
            del st.session_state[key]
    st.query_params.clear()


def validate_configuration():
    policy = load_policy()
    try:
        import authlib  # noqa: F401
        auth = st.secrets['auth']
        provider = auth['oidc']
        callback = urlsplit(auth['redirect_uri'])
        metadata = urlsplit(provider['server_metadata_url'])
        if not registry.middleware_ready or not st.get_option('server.enableXsrfProtection') or not st.get_option('server.enableCORS'):
            raise ValueError()
        if st.get_option('server.enableStaticServing') or st.get_option('server.baseUrlPath'):
            raise ValueError()
        if not isinstance(auth['cookie_secret'],str) or len(auth['cookie_secret']) < 32 or not isinstance(provider['client_secret'],str) or not provider['client_secret'].strip() or provider['client_id'] != policy['client_id']:
            raise ValueError()
        for url in (callback, metadata):
            if url.username or url.password or url.fragment or url.query or not url.hostname:
                raise ValueError()
            if url.scheme != 'https' and not (policy['environment'] == 'local' and url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')):
                raise ValueError()
        if callback.path != '/oauth2callback' or auth.get('expose_tokens') or provider.get('expose_tokens'):
            raise ValueError()
    except (ImportError, KeyError, TypeError, ValueError, FileNotFoundError):
        raise AccessUnavailable('Application access is unavailable.') from None
    return policy


def admitted_actor(*, controls=True):
    try:
        validate_configuration()
        if not st.user.is_logged_in:
            clear_view_state()
            st.title('PropertyAIgent')
            if st.button('Sign in'):
                st.login('oidc')
            st.stop()
        key = registry.fingerprint(st.context.cookies)
        actor = registry.issue(st.user.to_dict(), key, st.session_state.get('_access_lease'))
        st.session_state['_access_lease'] = actor
        if controls and st.sidebar.button('Sign out', key='_access_logout'):
            registry.revoke(key)
            clear_view_state()
            del st.session_state['_access_lease']
            st.logout()
            st.stop()
        return actor
    except AccessDenied as exc:
        clear_view_state()
        st.error(str(exc))
        if st.user.is_logged_in and st.button('Sign out'):
            st.logout()
            st.stop()
        st.stop()


@contextmanager
def page_scope():
    actor = admitted_actor()
    @st.fragment(run_every=20)
    def check_lifetime():
        # Automatic ticks check only; they never record user activity.
        try:
            registry.check(actor)
        except AccessDenied:
            clear_view_state()
            st.rerun(scope='app')
    check_lifetime()
    with actor_scope(actor):
        try:
            yield actor
        except AccessDenied as exc:
            clear_view_state()
            st.error(str(exc))
            st.stop()
