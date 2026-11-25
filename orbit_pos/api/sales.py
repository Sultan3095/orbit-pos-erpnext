import hashlib
import json
import frappe
from frappe.utils import flt, nowdate, getdate, now_datetime
from orbit_pos.logic.promotions import apply_promotions, r2
from orbit_pos.logic.returns import return_allowed, refund_amount, cross_branch_allowed
from orbit_pos.logic.loyalty import points_earned, redeem_value
from orbit_pos.logic.barcodes import make_ean13, parse_scale_barcode
from .common import require_pos_user, verify_manager_pin, log_approval, settings


def active_promotions():
    out = []
    for name in frappe.get_all("POS Promotion", filters={"enabled": 1}, pluck="name"):
        out.append(frappe.get_doc("POS Promotion", name).to_engine())
    return out


@frappe.whitelist()
def lookup(code):
    """Item by barcode, item code, or scale label. Returns qty for weighed labels."""
    require_pos_user()
    s = settings()
    scale = parse_scale_barcode(code)
    if scale:
        item = frappe.db.get_value("Item", {"orbit_plu": scale["plu"], "orbit_weighed": 1}, "name")
        if item and "qty" in scale:
            return {**_item_info(item), "qty": scale["qty"]}
    item = frappe.db.get_value("Item Barcode", {"barcode": code}, "parent") or \
        (code if frappe.db.exists("Item", code) else None)
    if not item:
        frappe.throw(frappe._("Item not found: {0}").format(code))
    return {**_item_info(item), "qty": 1}


def _item_info(item):
    d = frappe.db.get_value("Item", item, ["name", "item_name", "item_group", "has_serial_no", "has_batch_no",
                                           "orbit_weighed"], as_dict=True)
    d["price"] = flt(frappe.db.get_value("Item Price", {"item_code": item, "selling": 1}, "price_list_rate"))
    return d


@frappe.whitelist()
def next_barcode(item_code=None):
    """Atomic sequence on the settings doc. If item_code is given, the barcode is attached to the item."""
    require_pos_user()
    frappe.db.sql("select value from `tabSingles` where doctype='Orbit POS Settings' and field='barcode_seq' for update")
    s = frappe.get_doc("Orbit POS Settings")
    s.barcode_seq = (s.barcode_seq or 0) + 1
    s.save(ignore_permissions=True)
    code = make_ean13(s.barcode_seq, s.barcode_prefix or "200")
    if item_code:
        item = frappe.get_doc("Item", item_code)
        item.append("barcodes", {"barcode": code, "barcode_type": "EAN"})
        item.save()
    return code


def _compute(lines, customer_points=0, inv_pct=0, inv_amt=0):
    s = settings()
    pr = apply_promotions(lines, active_promotions(), now_datetime())
    sub = pr["subtotal"]
    manual_inv = r2(min(sub, (inv_amt or 0) + sub * (inv_pct or 0) / 100))
    redeem = redeem_value(customer_points, flt(s.value_per_point), max(0.0, sub - manual_inv - pr["invoicePromoDisc"]))
    inv_disc = r2(min(sub, manual_inv + pr["invoicePromoDisc"] + redeem))
    return {"lines": pr["lines"], "subtotal": sub, "invoice_discount": inv_disc, "redeem_value": redeem,
            "net_before_tax": r2(sub - inv_disc)}


@frappe.whitelist()
def quote(payload):
    """Server-side price calculation. The client displays this, it never decides totals."""
    require_pos_user()
    p = frappe.parse_json(payload)
    return _compute(p["lines"], p.get("redeem_points", 0), p.get("inv_pct", 0), p.get("inv_amt", 0))


def _check_discount_authority(p, shift):
    """Cashiers may not exceed the configured discount percent without a manager PIN."""
    if "POS Manager" in frappe.get_roles():
        return None
    limit = flt(settings().cashier_max_discount_percent)
    worst = 0
    for l in p["lines"]:
        worst = max(worst, flt(l.get("manualPct")))
    if flt(p.get("inv_pct")) > worst:
        worst = flt(p.get("inv_pct"))
    if worst > limit:
        mgr = verify_manager_pin(p.get("manager"), p.get("manager_pin"))
        log_approval(mgr, "Discount", p.get("txn_id"), f"{worst}% > {limit}%", shift)
        return mgr
    return None


@frappe.whitelist()
def submit_sale(payload):
    """Create a POS Sales Invoice. Safe to retry: the same txn_id and payload returns the same invoice."""
    require_pos_user()
    p = frappe.parse_json(payload)
    txn_id = p["txn_id"]
    body_hash = hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()
    prior = frappe.db.get_value("Offline Transaction", txn_id, ["payload_hash", "sales_invoice", "status"], as_dict=True)
    if prior:
        if prior.payload_hash != body_hash:
            frappe.throw(frappe._("Transaction id reused with different content"), frappe.DuplicateEntryError)
        return {"status": "duplicate", "sales_invoice": prior.sales_invoice}

    shift = p["shift"]
    sh = frappe.db.get_value("POS Shift", shift, ["status", "user", "shared_shift", "pos_profile", "branch"], as_dict=True)
    if not sh or sh.status != "Open":
        frappe.throw(frappe._("Shift is not open"))
    if sh.user != frappe.session.user and not sh.shared_shift:
        frappe.throw(frappe._("This shift belongs to another user"), frappe.PermissionError)
    _check_discount_authority(p, shift)

    customer = p.get("customer") or frappe.db.get_value("POS Profile", sh.pos_profile, "customer")
    pts = 0
    if p.get("redeem_points"):
        pts = min(int(p["redeem_points"]), _balance(customer))
    calc = _compute(p["lines"], pts, p.get("inv_pct", 0), p.get("inv_amt", 0))
    prof = frappe.get_doc("POS Profile", sh.pos_profile)

    si = frappe.new_doc("Sales Invoice")
    si.update({"customer": customer, "is_pos": 1, "update_stock": 1, "pos_profile": sh.pos_profile,
               "set_posting_time": 0, "company": prof.company, "orbit_txn_id": txn_id, "orbit_shift": shift,
               "orbit_branch": sh.branch, "currency": prof.currency, "selling_price_list": prof.selling_price_list,
               "set_warehouse": prof.warehouse,
               "discount_amount": calc["invoice_discount"], "apply_discount_on": "Net Total"})
    rates = []
    for src, l in zip(p["lines"], calc["lines"]):
        disc = r2(l["promoDisc"] + l["manualDisc"])
        unit_disc = disc / src["qty"] if src["qty"] else 0
        rates.append((src["price"], unit_disc))
        row = {"item_code": src["itemId"], "qty": src["qty"], "price_list_rate": src["price"],
               "rate": src["price"] - unit_disc,
               "discount_amount": unit_disc, "warehouse": prof.warehouse}
        if src.get("batch_no") or src.get("serial_no"):
            row["use_serial_batch_fields"] = 1   # v16 (and recent v15) read batch/serial from these fields
        if src.get("batch_no"):
            row["batch_no"] = src["batch_no"]
        if src.get("serial_no"):
            row["serial_no"] = "\n".join(src["serial_no"]) if isinstance(src["serial_no"], list) else src["serial_no"]
        si.append("items", row)
    # taxes come from the POS Profile tax template
    if prof.taxes_and_charges:
        si.taxes_and_charges = prof.taxes_and_charges
        si.set_taxes()
    si.set_missing_values()
    # set_missing_values re-reads the price list; the engine's price and discounts must win, and ERPNext only
    # keeps a discount_amount when the rate already reflects it
    for row, (price, unit_disc) in zip(si.items, rates):
        row.price_list_rate = price
        row.discount_amount = unit_disc
        row.rate = price - unit_disc
    si.set("payments", [])   # drop the profile's default zero-amount rows
    si.calculate_taxes_and_totals()

    paid = 0.0
    for pay in p["payments"]:
        si.append("payments", {"mode_of_payment": pay["method"], "amount": flt(pay["amount"])})
        paid += flt(pay["amount"])
    if paid + 0.005 < si.grand_total:
        frappe.throw(frappe._("Payments {0} are less than total {1}").format(paid, si.grand_total))
    change = r2(paid - si.grand_total)
    cash_rows = [r for r in si.payments if frappe.db.get_value("Mode of Payment", r.mode_of_payment, "type") == "Cash"]
    if change > 0:
        if not cash_rows:
            frappe.throw(frappe._("Change can only be given when part of the payment is cash"))
        cash_rows[0].amount = r2(cash_rows[0].amount - change)   # store cash net of change
    si.paid_amount = si.grand_total
    si.change_amount = 0
    si.write_off_amount = 0
    # safety net: the engine total (before tax) must match what ERPNext computed
    if abs(flt(si.net_total) - calc["net_before_tax"]) > 0.02 * max(1, len(si.items)) and not prof.taxes_and_charges:
        frappe.throw(frappe._("Totals mismatch between engine ({0}) and invoice ({1})").format(calc["net_before_tax"], si.net_total))
    si.insert()
    si.submit()

    if customer:
        earned = points_earned(si.grand_total, flt(settings().currency_per_point))
        if earned:
            _ledger(customer, earned, si.name, "earn")
        if pts:
            _ledger(customer, -pts, si.name, "redeem")
    frappe.get_doc({"doctype": "Offline Transaction", "txn_id": txn_id, "terminal": p.get("terminal"), "shift": shift,
                    "payload_hash": body_hash, "status": "Created", "sales_invoice": si.name}).insert(ignore_permissions=True)
    return {"status": "created", "sales_invoice": si.name, "grand_total": si.grand_total, "change": change}


def _balance(customer):
    if not customer:
        return 0
    return int(frappe.db.sql("select coalesce(sum(points),0) from `tabLoyalty Ledger Entry` where customer=%s", customer)[0][0])


def _ledger(customer, pts, inv, note):
    frappe.get_doc({"doctype": "Loyalty Ledger Entry", "customer": customer, "points": pts,
                    "sales_invoice": inv, "note": note}).insert(ignore_permissions=True)


@frappe.whitelist()
def create_return(invoice, items, manager=None, pin=None, current_branch=None):
    """items: [{item_code, qty}] (qty positive). Window and cross-branch rules come from Orbit POS Settings."""
    require_pos_user()
    s = settings()
    orig = frappe.get_doc("Sales Invoice", invoice)
    if orig.docstatus != 1 or orig.is_return:
        frappe.throw(frappe._("Cannot return this document"))
    if not cross_branch_allowed(orig.orbit_branch or "", current_branch or "", bool(s.allow_cross_branch_returns)):
        frappe.throw(frappe._("Returns from other branches are disabled in settings"))
    ok, needs_mgr = return_allowed(orig.posting_date, getdate(nowdate()), int(s.return_window_days or 0), manager_approved=False)
    approver = None
    if needs_mgr:
        if "POS Manager" in frappe.get_roles():
            approver = frappe.session.user
        else:
            approver = verify_manager_pin(manager, pin)
        log_approval(approver, "Return After Window", invoice, f"posted {orig.posting_date}")
    from erpnext.controllers.sales_and_purchase_return import make_return_doc
    ret = make_return_doc("Sales Invoice", invoice)
    want = {i["item_code"]: flt(i["qty"]) for i in frappe.parse_json(items)}
    ret.items = [r for r in ret.items if r.item_code in want]
    for r in ret.items:
        r.qty = -want[r.item_code]
    ret.orbit_branch = current_branch
    ret.orbit_shift = frappe.db.get_value("POS Shift", {"user": frappe.session.user, "status": "Open"}, "name")
    ret.update_stock = 1
    ret.calculate_taxes_and_totals()
    if ret.is_pos:
        # a POS return must refund through negative payment rows, so the cash drawer count stays right
        modes = [p.mode_of_payment for p in orig.payments]
        cash = [m for m in modes if frappe.db.get_value("Mode of Payment", m, "type") == "Cash"]
        ret.set("payments", [])
        ret.append("payments", {"mode_of_payment": (cash or modes or ["Cash"])[0], "amount": ret.grand_total})
        ret.paid_amount = ret.grand_total
    ret.insert()
    ret.submit()
    return {"return_invoice": ret.name, "refund": abs(ret.grand_total), "approved_by": approver}


def guard_invoice(doc, method=None):
    """Hook: a POS invoice must belong to an open shift (or be a return against one)."""
    if doc.get("orbit_shift") and not doc.is_return:
        if frappe.db.get_value("POS Shift", doc.orbit_shift, "status") != "Open":
            frappe.throw(frappe._("Shift is closed"))
