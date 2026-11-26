"""Gift cards and coupons. Same rules as the desktop app:
- A gift card sale is money held for the customer (a liability), not revenue. Revenue happens when the card pays a sale.
- A card is a payment method on the sale. A return gives the gift-paid share back to the card.
- A card can be voided only while unused. A sale paid with a card cannot be edited (void it or return).
- A coupon is a percent or amount off the subtotal after item promotions. One per invoice, lines become exchange-only."""
import frappe
from frappe.utils import flt, nowdate, getdate, add_days
from orbit_pos.logic.promotions import r2, coupon_amount
from .common import require_pos_user, log_approval, perm, can, approver_for, require

GIFT_MODE = "Gift Card"
LIABILITY = "Gift Card Liability"


def ensure_gift_mode(company):
    """Mode of Payment for the card: its account is a liability, never drawer cash."""
    if not frappe.db.exists("Mode of Payment", GIFT_MODE):
        frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": GIFT_MODE, "type": "General"}).insert(ignore_permissions=True)
    mop = frappe.get_doc("Mode of Payment", GIFT_MODE)
    if not [a for a in mop.accounts if a.company == company]:
        acc = frappe.db.get_value("Account", {"company": company, "account_name": LIABILITY, "is_group": 0}, "name")
        if not acc:
            parent = frappe.db.get_value("Account", {"company": company, "account_name": "Current Liabilities", "is_group": 1}, "name") or \
                frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name")
            acc = frappe.get_doc({"doctype": "Account", "account_name": LIABILITY, "company": company, "parent_account": parent,
                                  "is_group": 0, "root_type": "Liability", "account_type": "Bank"}).insert(ignore_permissions=True).name
        mop.append("accounts", {"company": company, "default_account": acc})
        mop.save(ignore_permissions=True)
    return GIFT_MODE


def _key(no):
    return str(no or "").strip().upper()


def _card(no, lock=False):
    k = _key(no)
    if not k or not frappe.db.exists("POS Gift Card", k):
        frappe.throw(frappe._("Gift card not found"), exc=frappe.DoesNotExistError)
    if lock:
        frappe.db.sql("select name from `tabPOS Gift Card` where name=%s for update", k)
    doc = frappe.get_doc("POS Gift Card", k)
    doc.reload()
    return doc


def _log(card, kind, amount, ref=""):
    frappe.get_doc({"doctype": "POS Gift Card Log", "card": card.name, "kind": kind, "amount": r2(amount),
                    "balance": r2(card.balance), "ref": ref}).insert(ignore_permissions=True)


def check_card(no, lock=False):
    """The card when it can pay now, else a readable error."""
    c = _card(no, lock)
    if c.status == "Void":
        frappe.throw(frappe._("This gift card was cancelled"))
    if c.status == "Written Off":
        frappe.throw(frappe._("This gift card balance was written off"))
    if c.expires_on and getdate(nowdate()) > getdate(c.expires_on):
        frappe.throw(frappe._("This gift card expired on {0}").format(c.expires_on))
    if not flt(c.balance) > 0.004:
        frappe.throw(frappe._("This gift card has no balance"))
    return c


def redeem(no, amount, ref):
    c = check_card(no, lock=True)
    amount = r2(min(flt(c.balance), amount))
    c.balance = r2(flt(c.balance) - amount)
    c.save(ignore_permissions=True)
    _log(c, "redeem", amount, ref)
    return amount


def give_back(no, amount, kind, ref):
    c = _card(no, lock=True)
    c.balance = r2(flt(c.balance) + amount)
    c.save(ignore_permissions=True)
    _log(c, kind, amount, ref)


def card_info(c):
    expired = bool(c.expires_on and getdate(nowdate()) > getdate(c.expires_on))
    state = "void" if c.status == "Void" else "writtenoff" if c.status == "Written Off" else "expired" if expired else "used" if not flt(c.balance) > 0 else "active"
    return {"card_no": c.name, "initial": flt(c.initial), "balance": flt(c.balance), "status": state, "issued_on": str(c.issued_on or ""),
            "expires_on": str(c.expires_on or ""), "customer_name": c.customer_name or ""}


@frappe.whitelist()
def check_gift_card(card_no):
    require_pos_user()
    return card_info(_card(card_no))


@frappe.whitelist()
def gift_card_history(card_no):
    require_pos_user()
    c = _card(card_no)
    return {**card_info(c), "log": frappe.get_all("POS Gift Card Log", filters={"card": c.name}, order_by="creation asc",
                                                   fields=["creation", "kind", "amount", "balance", "ref"])}


@frappe.whitelist()
def list_gift_cards(q=""):
    require_pos_user()
    rows = frappe.get_all("POS Gift Card", fields=["name"], order_by="creation desc", limit=500)
    out = []
    for r in rows:
        i = card_info(frappe.get_doc("POS Gift Card", r.name))
        if q and q.lower() not in (i["card_no"] + " " + i["customer_name"]).lower():
            continue
        out.append(i)
    liab = {"open": 0.0, "expired": 0.0, "count": 0}
    for i in out if not q else [card_info(frappe.get_doc("POS Gift Card", r.name)) for r in rows]:
        if i["status"] == "active":
            liab["open"] = r2(liab["open"] + i["balance"]); liab["count"] += 1
        elif i["status"] == "expired":
            liab["expired"] = r2(liab["expired"] + i["balance"])
    return {"cards": out, "liability": liab}


@frappe.whitelist()
def sell_gift_card(amount, shift, method="Cash", card_no=None, expires_days=0, customer_name="", ref=""):
    """Issue a card. The money goes to the paying method's account and to the Gift Card Liability account (a Journal Entry)."""
    require_pos_user()
    require("sellGiftCard")
    amount = r2(flt(amount))
    if not amount > 0:
        frappe.throw(frappe._("Gift card value must be more than zero"))
    sh = frappe.db.get_value("POS Shift", shift, ["status", "user", "shared_shift", "pos_profile"], as_dict=True)
    if not sh or sh.status != "Open":
        frappe.throw(frappe._("Shift is not open"))
    if sh.user != frappe.session.user and not sh.shared_shift:
        frappe.throw(frappe._("This shift belongs to another user"), frappe.PermissionError)
    if method in (GIFT_MODE, "Exchange Credit"):
        frappe.throw(frappe._("A gift card cannot be paid with credit or another gift card"))
    if not frappe.db.exists("Mode of Payment", method):
        frappe.throw(frappe._("Payment method {0} not found").format(method))
    co = frappe.db.get_value("POS Profile", sh.pos_profile, "company")
    no = _key(card_no)
    if no:
        import re
        if not re.fullmatch(r"[A-Z0-9-]{4,24}", no):
            frappe.throw(frappe._("Card number: 4 to 24 letters, digits or dashes"))
        if frappe.db.exists("POS Gift Card", no):
            frappe.throw(frappe._("A card with this number already exists"))
    else:
        import random
        while True:
            no = "GC" + str(random.randint(10000000, 99999999))
            if not frappe.db.exists("POS Gift Card", no):
                break
    pr = frappe.db.get_value("POS Printed Gift Card", no, ["name", "value"], as_dict=True) if no else None
    if pr and r2(flt(pr.value)) != amount:
        frappe.throw(frappe._("This printed card has a different value than the amount entered"))
    days = int(expires_days or 0)
    expires = add_days(nowdate(), days) if days > 0 else None
    mop = frappe.get_doc("Mode of Payment", method)
    pay_acc = next((a.default_account for a in mop.accounts if a.company == co), None)
    if not pay_acc:
        frappe.throw(frappe._("Payment method {0} has no account for {1}").format(method, co))
    ensure_gift_mode(co)
    liab = frappe.db.get_value("Account", {"company": co, "account_name": LIABILITY, "is_group": 0}, "name")
    cc = frappe.db.get_value("Company", co, "cost_center")
    je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": co, "posting_date": nowdate(),
                         "user_remark": f"Gift card {no} sold",
                         "accounts": [{"account": pay_acc, "debit_in_account_currency": amount, "cost_center": cc},
                                      {"account": liab, "credit_in_account_currency": amount, "cost_center": cc}]})
    je.insert(ignore_permissions=True)
    je.submit()
    c = frappe.get_doc({"doctype": "POS Gift Card", "card_no": no, "initial": amount, "balance": amount, "status": "Active",
                        "issued_on": nowdate(), "expires_on": expires, "customer_name": customer_name, "pay_method": method,
                        "shift": shift, "issued_by": frappe.session.user, "journal_entry": je.name})
    c.insert(ignore_permissions=True)
    _log(c, "issue", amount, ref or je.name)
    if pr:
        frappe.db.set_value("POS Printed Gift Card", pr.name, "sold_on", nowdate())
    return {**card_info(c), "journal_entry": je.name}


@frappe.whitelist()
def void_gift_card(card_no, reason="", manager=None, pin=None):
    """Cancel a card sold by mistake. Only an unused card, only while its shift is open."""
    require_pos_user()
    who = approver_for("voidGiftCard", manager, pin)
    c = _card(card_no, lock=True)
    if c.status == "Void":
        frappe.throw(frappe._("This gift card was cancelled"))
    if r2(flt(c.balance)) != r2(flt(c.initial)) or frappe.db.count("POS Gift Card Log", {"card": c.name}) > 1:
        frappe.throw(frappe._("This card was already used. It cannot be cancelled."))
    if c.shift and frappe.db.get_value("POS Shift", c.shift, "status") != "Open":
        frappe.throw(frappe._("The shift of this card sale is closed"))
    if c.journal_entry and frappe.db.get_value("Journal Entry", c.journal_entry, "docstatus") == 1:
        frappe.get_doc("Journal Entry", c.journal_entry).cancel()
    amount = flt(c.initial)
    c.status = "Void"; c.balance = 0
    c.save(ignore_permissions=True)
    _log(c, "void", amount, reason or "")
    log_approval(who, "Void Gift Card", c.name, reason or "", c.shift)
    return card_info(c)


BREAKAGE = "Gift Card Breakage Income"


def ensure_breakage_account(company):
    acc = frappe.db.get_value("Account", {"company": company, "account_name": BREAKAGE, "is_group": 0}, "name")
    if acc:
        return acc
    parent = frappe.db.get_value("Account", {"company": company, "account_name": "Indirect Income", "is_group": 1}, "name") or \
        frappe.db.get_value("Account", {"company": company, "root_type": "Income", "is_group": 1}, "name")
    return frappe.get_doc({"doctype": "Account", "account_name": BREAKAGE, "company": company, "parent_account": parent,
                           "is_group": 0, "root_type": "Income"}).insert(ignore_permissions=True).name


@frappe.whitelist()
def write_off_gift_card(card_no, reason="", manager=None, pin=None):
    """An expired card keeps its balance as a liability until a manager writes it off with a reason (Dr Gift Card Liability, Cr Breakage Income)."""
    require_pos_user()
    who = approver_for("voidGiftCard", manager, pin)
    if len(str(reason or "").strip()) < 3:
        frappe.throw(frappe._("Write the reason (3+ characters)"))
    c = _card(card_no, lock=True)
    if c.status == "Void":
        frappe.throw(frappe._("This gift card was cancelled"))
    if c.status == "Written Off":
        frappe.throw(frappe._("This gift card balance was written off"))
    if not (c.expires_on and getdate(nowdate()) > getdate(c.expires_on)):
        frappe.throw(frappe._("Only an expired card can be written off"))
    amount = r2(flt(c.balance))
    if not amount > 0.004:
        frappe.throw(frappe._("This gift card has no balance"))
    prof = frappe.db.get_value("POS Shift", c.shift, "pos_profile") if c.shift else None
    co = frappe.db.get_value("POS Profile", prof, "company") if prof else frappe.db.get_value("Account", {"account_name": LIABILITY, "is_group": 0}, "company")
    ensure_gift_mode(co)
    liab = frappe.db.get_value("Account", {"company": co, "account_name": LIABILITY, "is_group": 0}, "name")
    inc = ensure_breakage_account(co)
    cc = frappe.db.get_value("Company", co, "cost_center")
    je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": co, "posting_date": nowdate(),
                         "user_remark": f"Gift card {c.name} expired balance written off: {reason}",
                         "accounts": [{"account": liab, "debit_in_account_currency": amount, "cost_center": cc},
                                      {"account": inc, "credit_in_account_currency": amount, "cost_center": cc}]})
    je.insert(ignore_permissions=True)
    je.submit()
    c.balance = 0
    c.status = "Written Off"
    c.save(ignore_permissions=True)
    _log(c, "writeoff", amount, str(reason).strip() + " | " + je.name)
    log_approval(who, "Write Off Gift Card", c.name, str(reason).strip(), c.shift)
    return {**card_info(c), "journal_entry": je.name, "written_off": amount}


@frappe.whitelist()
def gift_by_value():
    """One row per card value: sold, fully used, partly used, unused, open and expired balance, written off. Cancelled cards are left out."""
    require_pos_user()
    today = getdate(nowdate())
    rows = {}
    for g in frappe.get_all("POS Gift Card", filters={"status": ["!=", "Void"]}, fields=["name", "initial", "balance", "status", "expires_on"], limit=100000):
        k = r2(flt(g.initial))
        r = rows.setdefault(k, {"value": k, "sold": 0, "sold_total": 0.0, "used": 0, "partly": 0, "untouched": 0, "open_count": 0, "open_balance": 0.0,
                                "expired_count": 0, "expired_balance": 0.0, "written_off_count": 0, "written_off_total": 0.0})
        r["sold"] += 1; r["sold_total"] = r2(r["sold_total"] + flt(g.initial))
        if g.status == "Written Off":
            wo = frappe.db.sql("select coalesce(sum(amount),0) from `tabPOS Gift Card Log` where card=%s and kind='writeoff'", g.name)[0][0]
            r["written_off_count"] += 1; r["written_off_total"] = r2(r["written_off_total"] + flt(wo))
            continue
        bal = r2(flt(g.balance))
        if not bal > 0.004:
            r["used"] += 1
            continue
        if bal == r2(flt(g.initial)):
            r["untouched"] += 1
        else:
            r["partly"] += 1
        if g.expires_on and today > getdate(g.expires_on):
            r["expired_count"] += 1; r["expired_balance"] = r2(r["expired_balance"] + bal)
        else:
            r["open_count"] += 1; r["open_balance"] = r2(r["open_balance"] + bal)
    out = sorted(rows.values(), key=lambda x: x["value"])
    total = {}
    for r in out:
        for k, v in r.items():
            if k != "value":
                total[k] = r2(total.get(k, 0) + v)
    return {"rows": out, "total": total}


@frappe.whitelist()
def print_gift_cards(value, qty):
    """A pool of card numbers to print. The value is printed on the card, so the sale checks it."""
    require_pos_user()
    require("sellGiftCard")
    value = r2(flt(value)); qty = int(qty or 0)
    if not value > 0:
        frappe.throw(frappe._("Gift card value must be more than zero"))
    if not 1 <= qty <= 500:
        frappe.throw(frappe._("Quantity must be 1 to 500"))
    import random
    out = []
    for _ in range(qty):
        while True:
            no = "GC" + str(random.randint(10000000, 99999999))
            if not frappe.db.exists("POS Gift Card", no) and not frappe.db.exists("POS Printed Gift Card", no):
                break
        frappe.get_doc({"doctype": "POS Printed Gift Card", "card_no": no, "value": value, "printed_on": nowdate()}).insert(ignore_permissions=True)
        out.append({"card_no": no, "value": value})
    return {"cards": out}


def shift_gifts(shift):
    """Cards sold in a shift per value, the cash part (in the drawer), and what customers paid with cards (no cash)."""
    by = {}
    for g in frappe.get_all("POS Gift Card", filters={"shift": shift, "status": ["!=", "Void"]}, fields=["initial"], limit=100000):
        k = r2(flt(g.initial)); r = by.setdefault(k, {"value": k, "count": 0, "total": 0.0})
        r["count"] += 1; r["total"] = r2(r["total"] + flt(g.initial))
    red = frappe.db.sql("""select coalesce(sum(p.amount),0) from `tabSales Invoice Payment` p join `tabSales Invoice` si on si.name=p.parent
        where si.orbit_shift=%s and si.docstatus=1 and si.is_return=0 and p.mode_of_payment=%s""", (shift, GIFT_MODE))[0][0]
    return {"by_value": sorted(by.values(), key=lambda x: x["value"]), "sold_cash": r2(cash_gift_sales(shift)), "redeemed": r2(flt(red))}


@frappe.whitelist()
def shift_gift_block(shift):
    require_pos_user()
    return shift_gifts(shift)


@frappe.whitelist()
def extend_gift_card(card_no, new_date=None):
    require_pos_user()
    require("voidGiftCard")
    c = _card(card_no, lock=True)
    if c.status == "Void":
        frappe.throw(frappe._("This gift card was cancelled"))
    c.expires_on = new_date or None
    c.save(ignore_permissions=True)
    _log(c, "expiry", 0, str(new_date or ""))
    return card_info(c)


def cash_gift_sales(shift):
    """Cash taken in for gift cards sold in this shift (cards not cancelled). Counted in the drawer."""
    row = frappe.db.sql("""select coalesce(sum(g.initial),0) from `tabPOS Gift Card` g
        where g.shift=%s and g.status='Active' and g.pay_method in (select name from `tabMode of Payment` where type='Cash')""", shift)
    return flt(row[0][0])


def gift_sold(shift):
    row = frappe.db.sql("select count(*), coalesce(sum(initial),0) from `tabPOS Gift Card` where shift=%s and status='Active'", shift)[0]
    return int(row[0]), flt(row[1])


# ---------------- coupons ----------------
def to_engine(doc):
    return {"code": doc.name, "kind": doc.kind, "value": flt(doc.value), "minTotal": flt(doc.min_total)}


def coupon_uses(code, customer=None):
    base = {"orbit_coupon": code, "docstatus": 1, "is_return": 0}
    allc = frappe.db.count("Sales Invoice", base)
    mine = frappe.db.count("Sales Invoice", {**base, "customer": customer}) if customer else 0
    return allc, mine


def check_coupon(code, customer=None, walkin=None):
    """The coupon doc when it can be used now, else a readable error. `walkin` is the default POS customer
    (a per-customer limit needs a real customer)."""
    k = _key(code)
    if not k or not frappe.db.exists("POS Coupon", k):
        frappe.throw(frappe._("Coupon not found"), exc=frappe.DoesNotExistError)
    c = frappe.get_doc("POS Coupon", k)
    if not c.enabled:
        frappe.throw(frappe._("This coupon is switched off"))
    today = getdate(nowdate())
    if c.start_date and today < getdate(c.start_date):
        frappe.throw(frappe._("This coupon starts on {0}").format(c.start_date))
    if c.end_date and today > getdate(c.end_date):
        frappe.throw(frappe._("This coupon expired on {0}").format(c.end_date))
    allc, mine = coupon_uses(c.name, customer)
    if c.max_uses and allc >= c.max_uses:
        frappe.throw(frappe._("This coupon has been used up"))
    if c.max_per_customer:
        if not customer or customer == walkin:
            frappe.throw(frappe._("This coupon needs a named customer"))
        if mine >= c.max_per_customer:
            frappe.throw(frappe._("This customer already used this coupon the allowed number of times"))
    return c


@frappe.whitelist()
def list_coupons():
    require_pos_user()
    rows = frappe.get_all("POS Coupon", fields=["name as code", "kind", "value", "min_total", "start_date", "end_date",
                                                "max_uses", "max_per_customer", "enabled"], order_by="creation desc")
    for r in rows:
        r["used"] = coupon_uses(r["code"])[0]
    return rows


@frappe.whitelist()
def save_coupon(data):
    require_pos_user()
    require("coupons")
    d = frappe.parse_json(data)
    import re
    code = re.sub(r"\s+", "", str(d.get("code") or "")).upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,20}", code):
        frappe.throw(frappe._("Coupon code: 3 to 20 letters, digits, dash or underscore"))
    kind = d.get("kind")
    if kind not in ("percent", "amount"):
        frappe.throw(frappe._("Coupon kind must be percent or amount"))
    v = flt(d.get("value"))
    if not v > 0 or (kind == "percent" and v > 100):
        frappe.throw(frappe._("Coupon value is not valid"))
    if d.get("start_date") and d.get("end_date") and str(d["end_date"]) < str(d["start_date"]):
        frappe.throw(frappe._("The end date is before the start date"))
    vals = {"kind": kind, "value": v, "min_total": flt(d.get("min_total")), "start_date": d.get("start_date") or None,
            "end_date": d.get("end_date") or None, "max_uses": int(d.get("max_uses") or 0),
            "max_per_customer": int(d.get("max_per_customer") or 0), "enabled": 0 if d.get("enabled") in (0, False, "0") else 1}
    if frappe.db.exists("POS Coupon", code):
        c = frappe.get_doc("POS Coupon", code); c.update(vals); c.save(ignore_permissions=True)
    else:
        c = frappe.get_doc({"doctype": "POS Coupon", "code": code, **vals}); c.insert(ignore_permissions=True)
    return {"code": c.name}


@frappe.whitelist()
def delete_coupon(code):
    require_pos_user()
    require("coupons")
    frappe.delete_doc("POS Coupon", _key(code), ignore_permissions=True)
    return {"deleted": _key(code)}
