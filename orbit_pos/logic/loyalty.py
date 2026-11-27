from .promotions import r2


def points_earned(net_total: float, currency_per_point: float) -> int:
    if currency_per_point <= 0:
        return 0
    return int(net_total // currency_per_point)


def redeem_value(points: int, value_per_point: float, max_value: float) -> float:
    return r2(min(max_value, points * value_per_point))


def phone_digits(s):
    return "".join(c for c in str(s or "") if c.isdigit())


def phone_matches(stored_numbers, entered, min_len=8):
    """True when the entered number matches one of the customer's numbers. Compares digit-only,
    accepting a country-code difference by suffix match (at least min_len digits)."""
    e = phone_digits(entered)
    if len(e) < min_len:
        return False
    for n in stored_numbers or []:
        s = phone_digits(n)
        if not s:
            continue
        if s == e or (len(s) >= min_len and (s.endswith(e) or e.endswith(s))):
            return True
    return False
