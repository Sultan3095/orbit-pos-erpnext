import frappe
from frappe.utils import now_datetime, flt
from .common import require_pos_user, verify_manager_pin, log_approval, settings, perm, can, approver_for


@frappe.whitelist()
def open_shift(pos_profile, opening_cash=0, terminal=None, shared=0, branch=None):
    """One open shift per user. shared=1 lets other users sell on this shift (managers only)."""
    require_pos_user()
    # one request at a time per user: a double click cannot create two open shifts
    frappe.db.sql("select name from `tabUser` where name=%s for update", frappe.session.user)
    if not frappe.db.exists("POS Profile", pos_profile):
        # the UI has no profile picker yet: fall back to the only enabled profile
        profiles = frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="name")
        if len(profiles) != 1:
            frappe.throw(frappe._("POS Profile {0} not found").format(pos_profile))
        pos_profile = profiles[0]
    if branch and not frappe.db.exists("Branch", branch):
        frappe.throw(frappe._("Branch {0} not found").format(branch))
    if int(shared or 0) and not can("approve"):
        frappe.throw(frappe._("Only a manager can open a shared shift"), frappe.PermissionError)
    if flt(opening_cash) < 0:
        frappe.throw(frappe._("Opening cash cannot be negative"))
    existing = frappe.db.sql("select name from `tabPOS Shift` where user=%s and status='Open' limit 1 for update", frappe.session.user)
    existing = existing[0][0] if existing else None
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
    from .gifts import cash_gift_sales
    return flt(row[0][0]) + cash_gift_sales(shift)


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
    sh = frappe.db.get_value("POS Shift", shift, ["status", "user", "shared_shift"], as_dict=True)
    if not sh or sh.status != "Open":
        frappe.throw(frappe._("Shift is closed"))
    if sh.user != frappe.session.user and not sh.shared_shift and not can("viewOtherShifts"):
        frappe.throw(frappe._("This shift belongs to another user"), frappe.PermissionError)
    approved = None
    from orbit_pos.api.common import settings
    if direction == "Out" and perm("cashOutAbove") != "Y" and amount > flt(settings().cashier_cash_out_limit):
        if perm("cashOutAbove") == "N":
            frappe.throw(frappe._("Your role may not take out this amount"), frappe.PermissionError)
        approved = verify_manager_pin(manager, pin)
        log_approval(approved, "Cash Out", shift, f"{amount} {reason}", shift)
    doc = frappe.get_doc({"doctype": "POS Cash Movement", "shift": shift, "direction": direction,
                          "amount": amount, "reason": reason, "approved_by": approved}).insert()
    return doc.as_dict()


@frappe.whitelist()
def close_shift(shift, counted_cash, note=None):
    """Users who may see the expected cash close normally. Users who may not (cashier by default) close BLIND:
    the count is saved, the shift is locked, expected cash and difference stay hidden, and the close waits for
    approve_close by a manager."""
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.status != "Open":
        frappe.throw(frappe._("Shift already closed"))
    if doc.user != frappe.session.user and not can("viewOtherShifts"):
        frappe.throw(frappe._("Only the shift owner or a manager can close it"), frappe.PermissionError)
    if flt(counted_cash) < 0:
        frappe.throw(frappe._("Counted cash cannot be negative"))
    exp = expected_cash(shift)
    doc.counted_cash = flt(counted_cash)
    doc.status = "Closed"
    doc.closed_at = now_datetime()
    if note:
        doc.notes = note
    if can("seeExpected"):
        doc.expected_cash = exp
        doc.approval_status = "Auto"
        doc.save()
        return _z_report(shift)
    doc.sealed_expected = exp
    doc.expected_cash = None
    doc.approval_status = "Pending"
    doc.save()
    return {"shift": shift, "pending": True, "counted_cash": doc.counted_cash}


def _approver_for_close(doc, manager, pin):
    me = frappe.session.user
    if can("approve", me) and can("seeExpected", me) and me != doc.user:
        return me
    who = verify_manager_pin(manager, pin)
    if not (can("approve", who) and can("seeExpected", who)):
        frappe.throw(frappe._("{0} may not approve a shift close").format(who), frappe.PermissionError)
    if who == doc.user:
        frappe.throw(frappe._("You cannot approve your own close"), frappe.PermissionError)
    return who


@frappe.whitelist()
def pending_close_view(shift, manager=None, pin=None):
    """What the approver sees before approving: expected vs counted vs difference."""
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.approval_status != "Pending":
        frappe.throw(frappe._("This close is not waiting for approval"))
    _approver_for_close(doc, manager, pin)
    diff = round(flt(doc.counted_cash) - flt(doc.sealed_expected), 2)
    threshold = flt(settings().get("second_approval_above"))
    return {"shift": shift, "user": doc.user, "expected_cash": flt(doc.sealed_expected), "counted_cash": flt(doc.counted_cash),
            "difference": diff, "note": doc.notes or "", "needs_second": bool(threshold > 0 and abs(diff) > threshold),
            "second_threshold": threshold}


@frappe.whitelist()
def approve_close(shift, note=None, manager=None, pin=None, second_manager=None, second_pin=None):
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.approval_status != "Pending":
        frappe.throw(frappe._("This close is not waiting for approval"))
    who = _approver_for_close(doc, manager, pin)
    diff = round(flt(doc.counted_cash) - flt(doc.sealed_expected), 2)
    if abs(diff) > 0.009 and not (note or "").strip() and not doc.notes:
        frappe.throw(frappe._("There is a difference. Write a note."))
    second = None
    threshold = flt(settings().get("second_approval_above"))
    if threshold > 0 and abs(diff) > threshold:
        # approved: a difference this large needs a second manager, never the first approver or the cashier
        second = verify_manager_pin(second_manager, second_pin)
        if not (can("approve", second) and can("seeExpected", second)):
            frappe.throw(frappe._("{0} may not approve a shift close").format(second), frappe.PermissionError)
        if second in (who, doc.user):
            frappe.throw(frappe._("The second approver must be a different manager"), frappe.PermissionError)
    doc.expected_cash = doc.sealed_expected
    doc.approval_status = "Approved"
    doc.approved_by = who
    doc.second_approved_by = second
    doc.approved_at = now_datetime()
    doc.approval_note = (note or "").strip()
    doc.save()
    log_approval(who, "Close Approval", shift, f"expected {doc.expected_cash} counted {doc.counted_cash} diff {diff}", shift)
    if second:
        log_approval(second, "Close Second Approval", shift, f"diff {diff} over threshold {threshold}", shift)
    return _z_report(shift)


@frappe.whitelist()
def send_back_for_recount(shift, note=None, manager=None, pin=None):
    """The approver disagrees with the count: back to the cashier for a recount, with a note. Approved flow."""
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.approval_status != "Pending":
        frappe.throw(frappe._("This close is not waiting for approval"))
    who = _approver_for_close(doc, manager, pin)
    if not (note or "").strip():
        frappe.throw(frappe._("Write what is wrong with the count"))
    doc.approval_status = "Recount"
    doc.approval_note = (note or "").strip()
    doc.save()
    log_approval(who, "Close Recount Request", shift, (note or "").strip(), shift)
    return {"shift": shift, "approval_status": "Recount"}


@frappe.whitelist()
def recount_shift(shift, counted_cash, note=None):
    """The cashier recounts after a send-back: same close, new count, back to Pending for approval."""
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.approval_status != "Recount":
        frappe.throw(frappe._("This close was not sent back for a recount"))
    if doc.user != frappe.session.user:
        frappe.throw(frappe._("Only the shift owner recounts"), frappe.PermissionError)
    if flt(counted_cash) < 0:
        frappe.throw(frappe._("Counted cash cannot be negative"))
    doc.counted_cash = flt(counted_cash)
    if (note or "").strip():
        doc.notes = ((doc.notes or "") + "\n" + note.strip()).strip()
    doc.approval_status = "Pending"
    doc.save()
    return {"shift": shift, "pending": True, "counted_cash": doc.counted_cash}


@frappe.whitelist()
def reopen_shift(shift, reason, manager=None, pin=None):
    """Cancel a shift close so invoices can be edited or voided. Needs the editInvoice permission (or an approver's PIN).
    The owner must have no other open shift. Close it again afterwards."""
    require_pos_user()
    if not (reason or "").strip():
        frappe.throw(frappe._("Reason is required"))
    doc = frappe.get_doc("POS Shift", shift)
    if doc.status != "Closed":
        frappe.throw(frappe._("Shift is not closed"))
    who = approver_for("editInvoice", manager, pin)
    if frappe.db.exists("POS Shift", {"user": doc.user, "status": "Open"}):
        frappe.throw(frappe._("{0} already has an open shift. Close it first.").format(doc.user))
    doc.status = "Open"
    doc.closed_at = None
    doc.counted_cash = None
    doc.expected_cash = None
    doc.sealed_expected = None
    doc.difference = None
    doc.approval_status = ""
    doc.reopen_count = int(doc.reopen_count or 0) + 1
    doc.reopened_by = who
    doc.reopen_reason = reason
    doc.save()
    log_approval(who, "Reopen Shift", shift, reason, shift)
    return {"shift": shift, "status": "Open", "reopen_count": doc.reopen_count}


def _z_report(shift):
    doc = frappe.get_doc("POS Shift", shift)
    pending = doc.approval_status in ("Pending", "Recount")   # sent-back counts stay hidden from the cashier too
    sales = frappe.db.sql("""select count(*), coalesce(sum(grand_total),0) from `tabSales Invoice`
        where orbit_shift=%s and docstatus=1 and is_return=0""", shift)[0]
    rets = frappe.db.sql("""select count(*), coalesce(sum(grand_total),0) from `tabSales Invoice`
        where orbit_shift=%s and docstatus=1 and is_return=1""", shift)[0]
    from .gifts import gift_sold, shift_gifts
    gifts_sold = gift_sold(shift)
    sg = shift_gifts(shift)
    return {"shift": shift, "user": doc.user, "opened_at": str(doc.opened_at), "closed_at": str(doc.closed_at or ""),
            "sales_count": sales[0], "sales_total": flt(sales[1]), "returns_count": rets[0],
            "returns_total": flt(rets[1]), "gift_sold_count": gifts_sold[0], "gift_sold_total": gifts_sold[1], "gift_by_value": sg["by_value"], "gift_sold_cash": sg["sold_cash"], "gift_redeemed": sg["redeemed"], "opening_cash": doc.opening_cash,
            "expected_cash": None if pending else doc.expected_cash, "counted_cash": doc.counted_cash,
            "difference": None if pending else doc.difference, "approval_status": doc.approval_status}


@frappe.whitelist()
def z_report(shift):
    """Z report of one shift: its owner, or a user who may view other shifts. Expected cash and the difference
    stay hidden from users who may not see them."""
    require_pos_user()
    doc = frappe.get_doc("POS Shift", shift)
    if doc.user != frappe.session.user and not can("viewOtherShifts"):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
    out = _z_report(shift)
    if not can("seeExpected"):
        out["expected_cash"] = None
        out["difference"] = None
    return out


@frappe.whitelist()
def my_permissions():
    """The current user's role and permission map, for the UI to show or hide controls. The server enforces every one."""
    require_pos_user()
    from .common import role_of, matrix, DEFAULTS
    role = role_of()
    return {"role": role, "perms": {k: perm(k) for k in DEFAULTS}, "user": frappe.session.user,
            "theme": frappe.db.get_value("DefaultValue", {"parent": frappe.session.user, "defkey": "orbit_theme"}, "defvalue") or ""}


THEMES = ("brand", "galaxy", "light", "dark")


@frappe.whitelist()
def set_theme(theme):
    """The user's own theme, kept on the server so it follows him to any screen. The default is the brand theme."""
    require_pos_user()
    if theme not in THEMES:
        frappe.throw(frappe._("Unknown theme"))
    frappe.defaults.set_user_default("orbit_theme", theme)
    return {"theme": theme}


@frappe.whitelist()
def pending_closes():
    """Blind closes waiting for approval. Approvers only. No amounts here: they are shown by pending_close_view."""
    require_pos_user()
    if not (can("approve") and can("seeExpected")):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
    return frappe.get_all("POS Shift", filters={"approval_status": "Pending", "status": "Closed"},
                          fields=["name", "user", "closed_at", "pos_profile"], order_by="closed_at desc")


@frappe.whitelist()
def my_recounts():
    """Closes of mine that a manager sent back for a recount, with the manager's note."""
    require_pos_user()
    return frappe.get_all("POS Shift", filters={"user": frappe.session.user, "approval_status": "Recount"},
                          fields=["name", "approval_note", "closed_at"], order_by="closed_at desc")
