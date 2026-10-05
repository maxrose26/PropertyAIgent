"""Small evidence-value contracts shared by search and buyer qualification."""
from decimal import Decimal, InvalidOperation


def known_unit_count(value):
    """Return an exact finite non-negative whole count, otherwise unknown."""
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = Decimal(str(value))
        if not numeric.is_finite() or numeric < 0 or numeric != numeric.to_integral_value():
            return None
        return int(numeric)
    except (InvalidOperation, ValueError, TypeError):
        return None
