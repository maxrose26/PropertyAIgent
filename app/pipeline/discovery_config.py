"""Fail-closed discovery admission; no environment mutation or DB access."""
import os


def is_production_runtime():
    return os.getenv('RENDER') == 'true' or bool(os.getenv('RENDER_SERVICE_ID'))


def discovery_switches():
    """Validate every value before applying disable-wins precedence.

    MODE is retained as a compatible safety input from specification 019.
    'bounded' never grants activation. ACTIVATED is a separate release gate.
    """
    values = {}
    for name in ('ACTIVATED', 'DISABLED'):
        raw = os.getenv('PROPERTYAIGENT_DISCOVERY_' + name, '0')
        if raw not in ('0', '1'):
            raise ValueError(f'invalid discovery {name}; expected 0 or 1')
        values[name.lower()] = raw == '1'
    mode = os.getenv('PROPERTYAIGENT_DISCOVERY_MODE', 'bounded')
    if mode not in ('bounded', 'disabled'):
        raise ValueError('invalid discovery MODE; expected bounded or disabled')
    values['disabled'] = values['disabled'] or mode == 'disabled'
    values['mode'] = 'disabled' if values['disabled'] else 'bounded'
    return values


def require_discovery_enabled():
    values = discovery_switches()
    if values['disabled']:
        raise RuntimeError('discovery disabled')
    if is_production_runtime() and not values['activated']:
        raise RuntimeError('P0-A production activation blocked')
    return values
