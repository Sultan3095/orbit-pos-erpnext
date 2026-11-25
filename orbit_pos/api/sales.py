import hashlib
import json
import json
import frappe
from frappe.utils import flt, nowdate, getdate, now_datetime
from orbit_pos.logic.promotions import apply_promotions, r2
from orbit_pos.logic.returns import return_allowed, refund_amount, cross_branch_allowed, credit_expiry, credit_expired, split_credit
from orbit_pos.logic.loyalty import points_earned, redeem_value
from orbit_pos.logic.barcodes import make_ean13, parse_scale_barcode
from .common import require_pos_user, verify_manager_pin, log_approval, settings, perm, can, approver_for


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
            "net_before_tax": r2(sub - inv_disc), "invoice_promo_disc": pr["invoicePromoDisc"]}


@frappe.whitelist()
def quote(payload):
    """Server-side price calculation. The client displays this, it never decides totals."""
    require_pos_user()
    p = frappe.parse_json(payload)
    return _compute(p["lines"], p.get("redeem_points", 0), p.get("inv_pct", 0), p.get("inv_amt", 0))


def _check_discount_authority(p, shift):
    """Cashiers may not exceed the configured discount percent without a manager PIN."""
    if perm("discountAbove") == "Y":
        return None
    limit = flt(settings().cashier_max_discount_percent)
    worst = 0
    for l in p["lines"]:
        worst = max(worst, flt(l.get("manualPct")))
    if flt(p.get("inv_pct")) > worst:
        worst = flt(p.get("inv_pct"))
    if worst > limit:
        if perm("discountAbove") == "N":
            frappe.throw(frappe._("Your role may not give this discount"), frappe.PermissionError)
        mgr = verify_manager_pin(p.get("manager"), p.get("manager_pin"))
        log_approval(mgr, "Discount", p.get("txn_id"), f"{worst}% > {limit}%", shift)
        return mgr
    return None


@frappe.whitelist()
def submit_sale(payload):
    """Create a POS Sales Invoice. Safe to retry: the same txn_id and payload returns the same invoice.
    Two requests with the same txn_id at the same moment (double tap, retry while the first is still running)
    must not fail: the loser waits for the winner's invoice and returns it as a duplicate."""
    try:
        return _submit_sale(payload)
    except frappe.UniqueValidationError:
        p = frappe.parse_json(payload)
        frappe.db.rollback()
        import time
        for _ in range(40):
            si = frappe.db.get_value("Sales Invoice", {"orbit_txn_id": p["txn_id"], "docstatus": 1}, "name")
            if si:
                return {"status": "duplicate", "sales_invoice": si}
            time.sleep(0.25)
            frappe.db.rollback()   # fresh snapshot for the next read
        raise


def _submit_sale(payload):
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
               "discount_amount": unit_disc, "warehouse": prof.warehouse,
               "orbit_promo": 1 if (l["promoDisc"] > 0 or calc["invoice_promo_disc"] > 0) else 0}
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
    rec, credit_used, credit_left = None, 0.0, 0.0
    if p.get("exchange_receipt"):
        rec = _open_receipt(p["exchange_receipt"])
        credit_used, credit_left = split_credit(flt(rec.amount), flt(si.grand_total))
        si.append("payments", {"mode_of_payment": ensure_credit_mode(prof.company), "amount": credit_used})
        paid += credit_used
    for pay in p["payments"]:
        si.append("payments", {"mode_of_payment": pay["method"], "amount": flt(pay["amount"]),
                               "orbit_ref": (pay.get("ref") or "")[:60]})
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

    new_receipt = None
    if rec:
        rec.db_set({"status": "Redeemed", "redeemed_in": si.name})
        if credit_left > 0.004:
            new_receipt = _issue_receipt(customer, credit_left, None, shift, rec.expires_on, source=rec.name).name
    if customer:
        earned = points_earned(si.grand_total, flt(settings().currency_per_point))
        if earned:
            _ledger(customer, earned, si.name, "earn")
        if pts:
            _ledger(customer, -pts, si.name, "redeem")
    frappe.get_doc({"doctype": "Offline Transaction", "txn_id": txn_id, "terminal": p.get("terminal"), "shift": shift,
                    "payload_hash": body_hash, "status": "Created", "sales_invoice": si.name}).insert(ignore_permissions=True)
    return {"status": "created", "sales_invoice": si.name, "grand_total": si.grand_total, "change": change,
            "exchange_credit_used": credit_used, "new_exchange_receipt": new_receipt}


def _balance(customer):
    if not customer:
        return 0
    return int(frappe.db.sql("select coalesce(sum(points),0) from `tabLoyalty Ledger Entry` where customer=%s", customer)[0][0])


def _ledger(customer, pts, inv, note):
    frappe.get_doc({"doctype": "Loyalty Ledger Entry", "customer": customer, "points": pts,
                    "sales_invoice": inv, "note": note}).insert(ignore_permissions=True)


CREDIT_MODE = "Exchange Credit"


def ensure_credit_mode(company):
    """Mode of Payment that carries exchange credit (a liability account, never counted as drawer cash)."""
    if not frappe.db.exists("Mode of Payment", CREDIT_MODE):
        frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": CREDIT_MODE, "type": "General"}).insert(ignore_permissions=True)
    mop = frappe.get_doc("Mode of Payment", CREDIT_MODE)
    if not [a for a in mop.accounts if a.company == company]:
        acc = frappe.db.get_value("Account", {"company": company, "account_name": "Exchange Credits", "is_group": 0}, "name")
        if not acc:
            parent = frappe.db.get_value("Account", {"company": company, "account_name": "Current Liabilities", "is_group": 1}, "name") or \
                frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name")
            acc = frappe.get_doc({"doctype": "Account", "account_name": "Exchange Credits", "company": company,
                                  "parent_account": parent, "is_group": 0, "root_type": "Liability",
                                  "account_type": "Bank"}).insert(ignore_permissions=True).name
        mop.append("accounts", {"company": company, "default_account": acc})
        mop.save(ignore_permissions=True)
    return CREDIT_MODE


def _issue_receipt(customer, amount, return_invoice, shift, expires_on=None, source=None):
    days = int(settings().return_window_days or 0)
    today = getdate(nowdate())
    if expires_on is None:
        expires_on = credit_expiry(today, days)
    doc = frappe.get_doc({"doctype": "POS Exchange Receipt", "customer": customer, "amount": r2(amount), "status": "Open",
                          "issued_on": today, "expires_on": expires_on, "return_invoice": return_invoice,
                          "shift": shift, "issued_by": frappe.session.user, "source_receipt": source})
    doc.insert(ignore_permissions=True)
    return doc


def _open_receipt(name):
    if not frappe.db.exists("POS Exchange Receipt", name):
        frappe.throw(frappe._("Exchange receipt {0} not found").format(name))
    rec = frappe.get_doc("POS Exchange Receipt", name)
    rec.reload()
    if rec.status != "Open":
        frappe.throw(frappe._("Exchange receipt {0} is already {1}").format(name, rec.status))
    if credit_expired(rec.expires_on, getdate(nowdate())):
        frappe.db.set_value("POS Exchange Receipt", name, "status", "Expired")
        frappe.throw(frappe._("Exchange receipt {0} expired on {1}").format(name, rec.expires_on))
    return rec


def row_serials(row):
    """Serial numbers of an invoice row, from the row text (v15/v16 serial fields) or its bundle."""
    import re
    if row.get("serial_no"):
        return [x.strip() for x in re.split(r"[\n,]", row.serial_no) if x.strip()]
    if row.get("serial_and_batch_bundle"):
        return frappe.get_all("Serial and Batch Entry", filters={"parent": row.serial_and_batch_bundle},
                              pluck="serial_no")
    return []


def returned_serials(orig_row_name):
    out = []
    for r in frappe.get_all("Sales Invoice Item", filters={"sales_invoice_item": orig_row_name, "docstatus": 1},
                            fields=["name", "serial_no", "serial_and_batch_bundle"]):
        out += row_serials(frappe._dict(r))
    return out


@frappe.whitelist()
def create_return(invoice, items, manager=None, pin=None, current_branch=None, mode="refund"):
    """items: [{item_code, qty, row?, serial_no?: [..]}] (qty positive).
    mode 'refund': money back through the original payment (never for promotion lines).
    mode 'credit': an Exchange Receipt for the value (promotion lines are exchange only).
    The window and cross-branch rules come from Orbit POS Settings."""
    require_pos_user()
    s = settings()
    if mode not in ("refund", "credit"):
        frappe.throw(frappe._("Unknown return mode"))
    orig = frappe.get_doc("Sales Invoice", invoice)
    if orig.docstatus != 1 or orig.is_return:
        frappe.throw(frappe._("Cannot return this document"))
    if not cross_branch_allowed(orig.orbit_branch or "", current_branch or "", bool(s.allow_cross_branch_returns)):
        frappe.throw(frappe._("Returns from other branches are disabled in settings"))
    ok, needs_mgr = return_allowed(orig.posting_date, getdate(nowdate()), int(s.return_window_days or 0), manager_approved=False)
    approver = None
    if needs_mgr:
        if perm("returnAfterWindow") == "N":
            frappe.throw(frappe._("Your role may not return after the window"), frappe.PermissionError)
        if can("returnAfterWindow"):
            approver = frappe.session.user
        else:
            approver = verify_manager_pin(manager, pin)
        log_approval(approver, "Return After Window", invoice, f"posted {orig.posting_date}")
    from erpnext.controllers.sales_and_purchase_return import make_return_doc
    ret = make_return_doc("Sales Invoice", invoice)
    by_row = {r.sales_invoice_item: r for r in ret.items}
    orig_rows = {r.name: r for r in orig.items}
    chosen, used = [], set()
    for it in frappe.parse_json(items):
        qty = flt(it.get("qty"))
        if qty <= 0:
            frappe.throw(frappe._("Return quantity must be positive"))
        rn = it.get("row")
        if not rn:
            cands = [n for n, r in by_row.items() if r.item_code == it.get("item_code") and n not in used]
            rn = cands[0] if cands else None
        if not rn or rn not in by_row or rn in used:
            frappe.throw(frappe._("Item {0} is not on this invoice or was already fully returned").format(it.get("item_code")))
        used.add(rn)
        r, o = by_row[rn], orig_rows[rn]
        if qty > abs(flt(r.qty)) + 1e-9:
            frappe.throw(frappe._("Cannot return {0} of {1}: only {2} left on this invoice").format(qty, r.item_code, abs(flt(r.qty))))
        if o.get("orbit_promo") and mode == "refund":
            frappe.throw(frappe._("{0} was sold under a promotion: exchange only, no cash refund").format(r.item_code))
        has_serial = frappe.db.get_value("Item", r.item_code, "has_serial_no")
        if has_serial:
            sel = it.get("serial_no") or []
            if isinstance(sel, str):
                sel = [x for x in sel.split("\n") if x.strip()]
            if not sel:
                frappe.throw(frappe._("Choose the serial numbers of {0} being returned").format(r.item_code))
            sold = set(row_serials(o)); back = set(returned_serials(o.name))
            for sn in sel:
                if sn not in sold:
                    frappe.throw(frappe._("Serial {0} was not sold on invoice {1}").format(sn, invoice))
                if sn in back:
                    frappe.throw(frappe._("Serial {0} was already returned").format(sn))
            if len(set(sel)) != len(sel) or len(sel) != qty:
                frappe.throw(frappe._("Serial numbers must be unique and match the quantity"))
            r.serial_and_batch_bundle = None
            r.use_serial_batch_fields = 1
            r.serial_no = "\n".join(sel)
        r.qty = -qty
        r.stock_qty = -qty * (flt(r.conversion_factor) or 1)
        chosen.append((r, o))
    if not chosen:
        frappe.throw(frappe._("Choose at least one item to return"))
    ret.items = [r for r, _ in chosen]
    for i, r in enumerate(ret.items, 1):
        r.idx = i
    # the invoice-level discount follows the share of the invoice being returned
    orig_net = sum(flt(o.qty) * flt(o.rate) for o in orig.items) or 1.0
    back_net = sum(qty_rate(r) for r, _ in chosen)
    ret.discount_amount = -flt(orig.discount_amount) * back_net / orig_net
    ret.orbit_branch = current_branch
    ret.orbit_shift = frappe.db.get_value("POS Shift", {"user": frappe.session.user, "status": "Open"}, "name")
    ret.update_stock = 1
    ret.calculate_taxes_and_totals()
    ret.set("payments", [])
    if mode == "credit":
        ret.append("payments", {"mode_of_payment": ensure_credit_mode(ret.company), "amount": ret.grand_total})
    else:
        modes = [p.mode_of_payment for p in orig.payments]
        cash = [m for m in modes if frappe.db.get_value("Mode of Payment", m, "type") == "Cash"]
        ret.append("payments", {"mode_of_payment": (cash or modes or ["Cash"])[0], "amount": ret.grand_total})
    ret.paid_amount = ret.grand_total
    ret.insert()
    ret.submit()
    receipt = None
    if mode == "credit":
        receipt = _issue_receipt(orig.customer, abs(ret.grand_total), ret.name, ret.orbit_shift).name
    return {"return_invoice": ret.name, "refund": abs(ret.grand_total), "approved_by": approver,
            "mode": mode, "exchange_receipt": receipt}


def qty_rate(r):
    return abs(flt(r.qty)) * flt(r.rate)


def guard_invoice(doc, method=None):
    """Hook: a POS invoice must belong to an open shift (or be a return against one)."""
    if doc.get("orbit_shift") and not doc.is_return:
        if frappe.db.get_value("POS Shift", doc.orbit_shift, "status") != "Open":
            frappe.throw(frappe._("Shift is closed"))


def guard_cancel(doc, method=None):
    """Hook: an invoice of a closed shift can never be cancelled or voided, from the POS or from the desk.
    Reopen the shift close first (needs approval), edit or void, then close again."""
    if doc.get("orbit_shift") and not doc.is_return:
        if frappe.db.get_value("POS Shift", doc.orbit_shift, "status") != "Open":
            frappe.throw(frappe._("The shift of this invoice is closed. Reopen the shift close first."))


def _editable_invoice(invoice):
    si = frappe.get_doc("Sales Invoice", invoice)
    if si.docstatus != 1 or si.is_return or not si.orbit_shift:
        frappe.throw(frappe._("This invoice cannot be edited or voided here"))
    if frappe.db.get_value("POS Shift", si.orbit_shift, "status") != "Open":
        frappe.throw(frappe._("The shift of this invoice is closed. Reopen the shift close first."))
    if frappe.db.exists("Sales Invoice", {"return_against": invoice, "docstatus": 1}):
        frappe.throw(frappe._("This invoice has returns. Edit is blocked."))
    if frappe.db.exists("POS Exchange Receipt", {"redeemed_in": invoice}):
        frappe.throw(frappe._("This invoice used an exchange receipt. Edit is blocked."))
    return si


def _reverse_loyalty(si):
    rows = frappe.db.sql("select customer, coalesce(sum(points),0) from `tabLoyalty Ledger Entry` where sales_invoice=%s group by customer", si.name)
    for cust, pts in rows:
        if pts:
            _ledger(cust, -int(pts), si.name, "reverse")


@frappe.whitelist()
def void_invoice(invoice, reason, manager=None, pin=None):
    """Cancel an invoice of an OPEN shift (stock and accounts are reversed). Never works on a closed shift."""
    require_pos_user()
    if not (reason or "").strip():
        frappe.throw(frappe._("Reason is required"))
    si = _editable_invoice(invoice)
    who = approver_for("voidInvoice", manager, pin)
    log_approval(who, "Void Invoice", invoice, reason, si.orbit_shift)
    _reverse_loyalty(si)
    si.cancel()
    return {"status": "voided", "invoice": invoice}


@frappe.whitelist()
def edit_invoice(invoice, payload, reason, manager=None, pin=None):
    """Edit = revision. The old invoice is cancelled (stock and accounts reversed) and a new one is created from the
    corrected payload (same shape as submit_sale, without txn_id), linked back with orbit_revision_of / orbit_rev.
    Only for an OPEN shift. Blocked when the invoice has returns or used an exchange receipt."""
    require_pos_user()
    if not (reason or "").strip():
        frappe.throw(frappe._("Reason is required"))
    si = _editable_invoice(invoice)
    who = approver_for("editInvoice", manager, pin)
    p = frappe.parse_json(payload)
    rev = int(si.get("orbit_rev") or 0) + 1
    root = si.get("orbit_revision_of") or si.name
    p["txn_id"] = f"{si.orbit_txn_id}-r{rev}"
    p["shift"] = si.orbit_shift
    p.setdefault("customer", si.customer)
    log_approval(who, "Edit Invoice", invoice, reason, si.orbit_shift)
    _reverse_loyalty(si)
    si.cancel()
    res = _submit_sale(json.dumps(p))
    frappe.db.set_value("Sales Invoice", res["sales_invoice"], {"orbit_revision_of": root, "orbit_rev": rev, "orbit_edit_reason": reason},
                        update_modified=False)
    res["revision_of"] = invoice
    res["rev"] = rev
    return res
