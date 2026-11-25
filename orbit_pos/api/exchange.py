"""Screens the cashier needs without ever opening the ERPNext desk: find a sale, return/exchange it,
pick a customer, see the active offers, and get the data to print a receipt."""
import frappe
from frappe.utils import flt, getdate, nowdate, now_datetime
from orbit_pos.logic.promotions import promo_active
from orbit_pos.logic.returns import return_allowed, credit_expired
from .common import require_pos_user, settings
from .sales import row_serials, returned_serials

WALKIN_AR, WALKIN_EN = "عميل نقدي", "Cash customer"


def _returned_qty(row_name):
    return flt(frappe.db.sql("""select coalesce(-sum(qty),0) from `tabSales Invoice Item`
        where sales_invoice_item=%s and docstatus=1""", row_name)[0][0])


@frappe.whitelist()
def search_invoices(q):
    """Find a sale by invoice number, customer name or phone, barcode/item code or serial number."""
    require_pos_user()
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = frappe.db.sql("""
        select distinct si.name, si.posting_date, si.posting_time, si.customer, si.customer_name, si.grand_total
        from `tabSales Invoice` si
        left join `tabSales Invoice Item` it on it.parent = si.name
        left join `tabItem Barcode` bc on bc.parent = it.item_code
        left join `tabCustomer` c on c.name = si.customer
        where si.docstatus = 1 and si.is_return = 0 and si.orbit_shift is not null
          and (si.name like %(l)s or si.customer_name like %(l)s or c.mobile_no like %(l)s
               or it.item_code = %(q)s or bc.barcode = %(q)s or it.serial_no like %(l)s or it.item_name like %(l)s)
        order by si.posting_date desc, si.posting_time desc limit 20""", {"l": like, "q": q}, as_dict=True)
    for r in rows:
        r["posting_date"] = str(r["posting_date"]); r["posting_time"] = str(r["posting_time"])
    return rows


@frappe.whitelist()
def invoice_for_return(invoice):
    """Everything the returns screen shows: lines with what is left to return, serials, promo flag, window state."""
    require_pos_user()
    s = settings()
    si = frappe.get_doc("Sales Invoice", invoice)
    if si.docstatus != 1 or si.is_return:
        frappe.throw(frappe._("Not a sale invoice"))
    window = int(s.return_window_days or 0)
    age = (getdate(nowdate()) - getdate(si.posting_date)).days
    _, needs_mgr = return_allowed(si.posting_date, getdate(nowdate()), window)
    lines = []
    for r in si.items:
        back = _returned_qty(r.name)
        serials = []
        if frappe.db.get_value("Item", r.item_code, "has_serial_no"):
            gone = set(returned_serials(r.name))
            serials = [x for x in row_serials(r) if x not in gone]
        lines.append({"row": r.name, "item_code": r.item_code, "item_name": r.item_name, "qty": flt(r.qty),
                      "returned": back, "left": flt(r.qty) - back, "rate": flt(r.rate),
                      "promo": bool(r.get("orbit_promo")), "has_serial": bool(frappe.db.get_value("Item", r.item_code, "has_serial_no")),
                      "serials": serials})
    return {"invoice": si.name, "date": str(si.posting_date), "customer": si.customer, "customer_name": si.customer_name,
            "grand_total": flt(si.grand_total), "branch": si.orbit_branch, "age_days": age, "window_days": window,
            "needs_manager": needs_mgr, "lines": lines}


@frappe.whitelist()
def exchange_receipt_info(name):
    """Look up an exchange receipt before the cashier applies it to a sale."""
    require_pos_user()
    if not frappe.db.exists("POS Exchange Receipt", name):
        frappe.throw(frappe._("Exchange receipt {0} not found").format(name))
    d = frappe.get_doc("POS Exchange Receipt", name)
    expired = credit_expired(d.expires_on, getdate(nowdate()))
    return {"name": d.name, "amount": flt(d.amount), "status": "Expired" if (expired and d.status == "Open") else d.status,
            "customer": d.customer, "expires_on": str(d.expires_on or ""), "issued_on": str(d.issued_on or "")}


@frappe.whitelist()
def search_customers(q=""):
    require_pos_user()
    like = f"%{(q or '').strip()}%"
    return frappe.db.sql("""select name, customer_name, mobile_no from `tabCustomer`
        where disabled = 0 and (customer_name like %(l)s or mobile_no like %(l)s or name like %(l)s)
        order by customer_name limit 15""", {"l": like}, as_dict=True)


@frappe.whitelist()
def create_customer(customer_name, mobile_no=None):
    require_pos_user()
    if not (customer_name or "").strip():
        frappe.throw(frappe._("Customer name is required"))
    grp = frappe.db.get_single_value("Selling Settings", "customer_group") or frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
    terr = frappe.db.get_single_value("Selling Settings", "territory") or frappe.db.get_value("Territory", {"is_group": 0}, "name")
    doc = frappe.get_doc({"doctype": "Customer", "customer_name": customer_name.strip(), "customer_group": grp,
                          "territory": terr, "mobile_no": mobile_no or None, "customer_type": "Individual"})
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "customer_name": doc.customer_name, "mobile_no": doc.mobile_no}


@frappe.whitelist()
def active_promotions():
    """Offers running right now (enabled, inside the dates, on today's weekday) for the cashier screen."""
    require_pos_user()
    out = []
    for name in frappe.get_all("POS Promotion", filters={"enabled": 1}, pluck="name"):
        doc = frappe.get_doc("POS Promotion", name)
        e = doc.to_engine()
        if not promo_active(e, now_datetime()):
            continue
        p = e["params"]
        scope = {"all": "", "item": e["scope"].get("value", ""), "group": e["scope"].get("value", "")}[e["scope"]["type"]]
        out.append({"name": doc.promo_name, "type": doc.promo_type, "scope_type": e["scope"]["type"], "scope": scope,
                    "buy": p["buy"], "get": p["get"], "get_pct": p["getPct"], "percent": p["percent"], "amount": p["amount"],
                    "bundle_qty": p["qty"], "bundle_price": p["price"], "min_total": p["minTotal"],
                    "end": e["end"]})
    return out


@frappe.whitelist()
def get_receipt(invoice):
    """Data for the printed receipt of a sale, or of a return/exchange (with its exchange receipt)."""
    require_pos_user()
    s = settings()
    si = frappe.get_doc("Sales Invoice", invoice)
    prof = frappe.get_doc("POS Profile", si.pos_profile) if si.pos_profile else None
    walkin = prof.customer if prof else None
    is_walkin = (not si.customer) or si.customer == walkin
    lines = [{"name": r.item_name, "qty": flt(r.qty), "rate": flt(r.rate), "amount": flt(r.amount),
              "promo": bool(r.get("orbit_promo")), "serial": ", ".join(row_serials(r))} for r in si.items]
    pays = [{"method": p.mode_of_payment, "amount": flt(p.amount)} for p in si.payments]
    out = {"invoice": si.name, "is_return": bool(si.is_return), "against": si.return_against, "date": str(si.posting_date),
           "time": str(si.posting_time)[:5], "company": si.company, "branch": si.orbit_branch or "",
           "cashier": frappe.db.get_value("User", si.owner, "full_name") or si.owner,
           "customer": WALKIN_AR if is_walkin else si.customer_name, "customer_en": WALKIN_EN if is_walkin else si.customer_name,
           "lines": lines, "net_total": flt(si.net_total), "discount": flt(si.discount_amount),
           "taxes": [{"name": t.description, "amount": flt(t.tax_amount)} for t in si.taxes],
           "grand_total": flt(si.grand_total), "payments": pays,
           "format": (prof.get("orbit_return_receipt_format") if si.is_return else prof.get("orbit_sale_receipt_format")) if prof else "Standard 80mm",
           "window_days": int(s.return_window_days or 0), "terms_ar": s.receipt_terms_ar or "", "terms_en": s.receipt_terms_en or "",
           "exchange_receipt": None}
    if si.is_return:
        rec = frappe.db.get_value("POS Exchange Receipt", {"return_invoice": si.name}, ["name", "amount", "expires_on", "issued_on"], as_dict=True)
        if rec:
            out["exchange_receipt"] = {"name": rec.name, "amount": flt(rec.amount), "expires_on": str(rec.expires_on or ""),
                                       "issued_on": str(rec.issued_on or "")}
    else:
        used = frappe.db.get_value("POS Exchange Receipt", {"redeemed_in": si.name}, ["name", "amount"], as_dict=True)
        if used:
            out["exchange_credit_used"] = {"name": used.name, "amount": flt(used.amount)}
    return out
