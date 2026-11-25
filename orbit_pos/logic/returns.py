"""Return rules: window check with manager bypass, pro-rata refund."""
from datetime import date, datetime
from .promotions import r2


def return_allowed(sale_date, today=None, window_days: int = 14, manager_approved: bool = False):
    """Returns (allowed, needs_manager)."""
    today = today or date.today()
    if isinstance(sale_date, datetime):
        sale_date = sale_date.date()
    if isinstance(sale_date, str):
        sale_date = date.fromisoformat(sale_date[:10])
    age = (today - sale_date).days
    if window_days <= 0 or age <= window_days:
        return True, False
    return (True, True) if manager_approved else (False, True)


def refund_amount(line_net_paid: float, line_qty: float, return_qty: float,
                  already_returned_qty: float = 0.0) -> float:
    """Pro-rata of what was actually paid for the line (after discounts)."""
    left = line_qty - already_returned_qty
    if return_qty <= 0 or return_qty > left + 1e-9:
        raise ValueError("invalid return quantity")
    # cumulative rounding: total refunded after this return minus total refunded before,
    # so several partial returns always add up to exactly what was paid
    after = r2(line_net_paid * (already_returned_qty + return_qty) / line_qty)
    before = r2(line_net_paid * already_returned_qty / line_qty)
    return r2(after - before)


def cross_branch_allowed(sale_branch: str, current_branch: str, allow_cross: bool) -> bool:
    return sale_branch == current_branch or bool(allow_cross)
