from .promotions import r2


def points_earned(net_total: float, currency_per_point: float) -> int:
    if currency_per_point <= 0:
        return 0
    return int(net_total // currency_per_point)


def redeem_value(points: int, value_per_point: float, max_value: float) -> float:
    return r2(min(max_value, points * value_per_point))
