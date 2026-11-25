import frappe
from frappe.utils import now_datetime, flt
from .common import require_pos_user, verify_manager_pin, log_approval, settings


@frappe.whitelist()
def open_shift(pos_profile, opening_cash=0, terminal=None, shared=0, branch=None):
    """One open shift per user. With shared=1, other terminals can join the same shift by passing its name to join_shift."""
    require_pos_user()
    existing = frappe.db.get_value("POS Shift", {"user": frappe.session.user, "status": "Open"}, "name")
    if existing:
        frappe.throw(frappe._("You already have an open shift: {0}").format(existing))
    doc = frappe.get_doc({"doctype": "POS Shift", "user": frappe.session.user, "pos_profile": pos_profile,
                          "terminal": terminal, "branch": branch, "shared_shift": int(shared),
                          "opening_cash": flt(opening_cash), "status": "Open", "opened_at": now_datetime()})
    doc.insert()
    return doc.as_dict()


@frappe.whitelist()
def current_shift():
    require_pos_user()
    name = frappe.db.get_value("POS Shift", {"user": frappe.session.user, "status": "Open"}, "name")
    return frappe.get_doc("POS Shift", name).as_dict() if name else None


def _cash_sales(shift):
    row = frappe.db.sql("""select coalesce(sum(sip.amount),0) from `tabSales Invoice Payment` sip
        join `tabSales Invoice` si on si.name = sip.parent
        where si.orbit_shift=%s and si.docstatus=1 and sip.mode_of_payment in
        (select name from `tabMode of Payment` where type='Cash')""", shift)
    return flt(row[0][0])


def expected_cash(shift):
    doc = frappe.get_doc("POS Shift", shift)
    moves = frappe.get_all("POS Cash Movement", filters={"shift": shift}, fields=["direction", "amount"])
    cash_in = sum(flt(m.amount) for m in moves if m.direction == "In")
    cash_out = sum(flt(m.amount) for m in moves if m.direction == "Out")
    # cash sales are net of change given (payments rows are stored net by submit_sale) and of cash refunds
    return flt(doc.opening_cash) + _cash_sales(shift) + cash_in - cash_out


@frappe.whitelist()
def cash_movement(shift, direction, amount, reason, manager=None, pin=None):
    require_pos_user()
    amount = flt(amount)
    if direction not in ("In", "Out") or amount <= 0 or not reason:
        frappe.throw(frappe._("Direction, positive amount and reason are required"))
    if frappe.db.get_value("POS Shift", shift, "status") != "Open":
        frappe.throw(frappe._("Shift is closed"))
    approved = None
    if direction == "Out" and "POS Manager" not in frappe.get_roles():
        approved = verify_manager_pin(manager, pin)
        log_approval(approved, "Cash Out", shift, f"{amount} {reason}", shift)
    doc = frappe.get_doc({"doctype": "POS Cash Movement", "shift": shift, "direction": direction,
                          "amount": amount, "reason": reason, "approved_by": approved}).insert()
    return doc.as_dict()


@frappe.whitelist()
def close_shift(shift, counted_cash):
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.status != "Open":
        frappe.throw(frappe._("Shift already closed"))
    if doc.user != frappe.session.user and "POS Manager" not in frappe.get_roles():
        frappe.throw(frappe._("Only the shift owner or a manager can close it"), frappe.PermissionError)
    doc.expected_cash = expected_cash(shift)
    doc.counted_cash = flt(counted_cash)
    doc.status = "Closed"
    doc.closed_at = now_datetime()
    doc.save()
    return z_report(shift)


@frappe.whitelist()
def z_report(shift):
    doc = frappe.get_doc("POS Shift", shift)
    sales = frappe.db.sql("""select count(*), coalesce(sum(grand_total),0) from `tabSales Invoice`
        where orbit_shift=%s and docstatus=1 and is_return=0""", shift)[0]
    rets = frappe.db.sql("""select count(*), coalesce(sum(grand_total),0) from `tabSales Invoice`
        where orbit_shift=%s and docstatus=1 and is_return=1""", shift)[0]
    return {"shift": shift, "user": doc.user, "opened_at": str(doc.opened_at), "closed_at": str(doc.closed_at or ""),
            "sales_count": sales[0], "sales_total": flt(sales[1]), "returns_count": rets[0],
            "returns_total": flt(rets[1]), "opening_cash": doc.opening_cash,
            "expected_cash": doc.expected_cash, "counted_cash": doc.counted_cash, "difference": doc.difference}
