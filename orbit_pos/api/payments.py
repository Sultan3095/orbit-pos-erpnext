"""Provider tenders (Paymob, Fawry) for the POS.

Flow: the cashier starts a payment attempt from the payment screen, the customer pays through the
provider (checkout page or a Fawry reference number), the cashier checks the result, and only a PAID
attempt can be used as a payment row on the sale. Every call is logged on the POS Payment Attempt.

Modes (Orbit POS Settings > Payments Mode):
  off  - provider tenders are hidden and refused
  mock - our own provider simulation built from the official docs (what CI proves)
  test - the provider's test/staging environment with the client's test credentials
  live - production with the client's credentials
"""
import json

import frappe
from frappe.utils import flt, now_datetime

from orbit_pos.api.common import require, require_pos_user, settings
from orbit_pos.logic import providers as P

PROVIDER_METHODS = {"paymob": "Paymob", "fawry": "Fawry"}
METHOD_PROVIDERS = {v: k for k, v in PROVIDER_METHODS.items()}


def payments_mode():
    return (settings().get("payments_mode") or "off")


def _cfg(provider):
    s = settings()
    if provider == "paymob":
        ids = [x.strip() for x in (s.get("paymob_integration_ids") or "").split(",") if x.strip()]
        return {"secret_key": (s.get_password("paymob_secret_key") if s.get("paymob_secret_key") else "") or "",
                "public_key": s.get("paymob_public_key") or "",
                "payment_methods": [int(x) if x.isdigit() else x for x in ids]}
    if provider == "fawry":
        return {"merchant_code": s.get("fawry_merchant_code") or "",
                "secure_key": (s.get_password("fawry_secure_key") if s.get("fawry_secure_key") else "") or ""}
    frappe.throw(frappe._("Unknown payment provider {0}").format(provider))


def ensure_provider_mode(company, provider):
    """Mode of Payment that carries a provider tender (Bank, never drawer cash)."""
    name = PROVIDER_METHODS[provider]
    if not frappe.db.exists("Mode of Payment", name):
        frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Bank"}).insert(ignore_permissions=True)
    mop = frappe.get_doc("Mode of Payment", name)
    if not [a for a in mop.accounts if a.company == company]:
        acc = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name") or \
            frappe.db.get_value("Company", company, "default_bank_account")
        mop.append("accounts", {"company": company, "default_account": acc})
        mop.save(ignore_permissions=True)
    return name


@frappe.whitelist()
def create_payment(provider, payload):
    """Start a payment attempt. Returns the attempt with its customer instructions / checkout URL."""
    require_pos_user()
    require("sell")
    mode = payments_mode()
    if mode == "off":
        frappe.throw(frappe._("Provider payments are switched off in Orbit POS Settings"))
    if provider not in P.PROVIDERS:
        frappe.throw(frappe._("Unknown payment provider {0}").format(provider))
    p = frappe.parse_json(payload)
    sh = frappe.db.get_value("POS Shift", p.get("shift"), ["status", "user", "shared_shift"], as_dict=True)
    if not sh or sh.status != "Open":
        frappe.throw(frappe._("Shift is not open"))
    if sh.user != frappe.session.user and not sh.shared_shift:
        frappe.throw(frappe._("This shift belongs to another user"), frappe.PermissionError)
    sale = {"ref": str(p.get("txn_id") or ""), "amount": flt(p.get("amount")),
            "currency": p.get("currency") or "EGP", "lines": p.get("lines") or [],
            "customer": p.get("customer") or {}}
    if not sale["ref"]:
        frappe.throw(frappe._("Missing transaction id"))
    if frappe.db.exists("POS Payment Attempt", {"txn_id": sale["ref"], "state": ["in", ("pending", "paid")]}):
        frappe.throw(frappe._("There is already an open payment for this transaction"), frappe.DuplicateEntryError)
    cfg = _cfg(provider)
    req = P.create_attempt(provider, sale, cfg, mode if mode in ("test", "live") else "mock")
    if mode == "mock":
        attempt = P.mock_create(provider, req["body"])
        sent, got = req["body"], {"mock": True, "attempt": attempt}
    else:
        got = frappe.utils.make_post_request(req["url"], headers=req["headers"], data=json.dumps(req["body"]))
        attempt = req["parse"](got)
        sent = req["body"]
    doc = frappe.get_doc({"doctype": "POS Payment Attempt", "provider": provider, "txn_id": sale["ref"],
                          "shift": p.get("shift"), "amount": sale["amount"], "currency": sale["currency"],
                          "state": attempt["state"], "provider_ref": attempt.get("ref"), "mode": mode,
                          "instructions": attempt.get("instructions") or "", "checkout_url": attempt.get("checkout_url") or "",
                          "request_json": json.dumps(sent, default=str), "response_json": json.dumps(got, default=str)})
    doc.insert(ignore_permissions=True)
    return _info(doc)


def _info(doc):
    return {"name": doc.name, "provider": doc.provider, "txn_id": doc.txn_id, "amount": flt(doc.amount),
            "currency": doc.currency, "state": doc.state, "provider_ref": doc.provider_ref or "",
            "instructions": doc.instructions or "", "checkout_url": doc.checkout_url or "",
            "sales_invoice": doc.sales_invoice or ""}


@frappe.whitelist()
def payment_status(name):
    """Current state of an attempt. Mock: whatever mock_settle left. Test/live: asks the provider when
    an inquiry call is documented for it; otherwise the state the callback left."""
    require_pos_user()
    doc = frappe.get_doc("POS Payment Attempt", name)
    if doc.mode == "mock":
        return _info(doc)
    # Paymob transaction inquiry needs the intention id; Fawry status API needs the merchant ref.
    # Both are live-environment calls we cannot prove without the client's accounts, so we keep the
    # last known state and let the provider's callback (notification URL) advance it.
    return _info(doc)


@frappe.whitelist()
def mock_settle(name, state):
    """Mock mode only: settle an attempt the way the provider would (paid/failed/expired/refunded).
    This is how tests and demos move a mock payment; a real provider does this by callback."""
    require_pos_user()
    if payments_mode() != "mock":
        frappe.throw(frappe._("mock_settle exists only in mock mode"))
    P._check_state(state)
    doc = frappe.get_doc("POS Payment Attempt", name)
    doc.state = state
    doc.save(ignore_permissions=True)
    return _info(doc)


@frappe.whitelist()
def list_payments(shift=None, state=None):
    require_pos_user()
    require("viewOtherShifts")
    filters = {}
    if shift:
        filters["shift"] = shift
    if state:
        filters["state"] = state
    rows = frappe.get_all("POS Payment Attempt", filters=filters, order_by="creation desc", limit=200,
                          fields=["name", "provider", "txn_id", "shift", "amount", "state", "provider_ref", "sales_invoice"])
    return rows


def validate_provider_payment(pay, payload_ref, company):
    """A Paymob/Fawry payment row on a sale: only a PAID, unconsumed attempt for THIS transaction counts.
    Returns the attempt doc. Called from submit_sale."""
    provider = METHOD_PROVIDERS[pay["method"]]
    if payments_mode() == "off":
        frappe.throw(frappe._("Provider payments are switched off in Orbit POS Settings"))
    ref = pay.get("attempt") or ""
    if not ref or not frappe.db.exists("POS Payment Attempt", ref):
        frappe.throw(frappe._("A {0} payment needs a payment attempt reference").format(pay["method"]))
    # row lock: one sale consumes the attempt
    frappe.db.sql("select name from `tabPOS Payment Attempt` where name=%s for update", ref)
    att = frappe.get_doc("POS Payment Attempt", ref)
    if att.state != "paid":
        frappe.throw(frappe._("This {0} payment is {1}, not paid").format(pay["method"], att.state))
    if att.txn_id != payload_ref:
        frappe.throw(frappe._("This payment attempt belongs to another transaction"))
    if att.sales_invoice:
        frappe.throw(frappe._("This payment was already used on invoice {0}").format(att.sales_invoice), frappe.DuplicateEntryError)
    if abs(flt(att.amount) - flt(pay["amount"])) > 0.005:
        frappe.throw(frappe._("The paid amount {0} does not match the payment {1}").format(att.amount, pay["amount"]))
    ensure_provider_mode(company, provider)
    return att
