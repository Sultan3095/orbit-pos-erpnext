"""ETA e-receipt queue (Egyptian Tax Authority).

When ETA is enabled in Orbit POS Settings, every submitted POS Sales Invoice becomes a Receipt v1.2
document queued as a POS ETA Receipt. Submitting signs the document through the pluggable signer and
sends it; results come back per receipt (accepted with a long id, or rejected with the reason).

Environments (Orbit POS Settings > ETA Environment):
  mock    - our own submission endpoint built from the docs; the only thing CI can prove
  Preprod / Prod - the real ETA endpoints. These need the client's tax registration, a POS registered
  on pos.eta.gov.eg and the client's signing certificate, none of which we have, so the live path
  refuses with a clear message until those exist.
"""
import json

import frappe
from frappe.utils import flt, now_datetime

from orbit_pos.api.common import require, require_pos_user, settings
from orbit_pos.logic import eta as E


def eta_enabled():
    return bool(settings().get("eta_enabled"))


def _seller():
    s = settings()
    return {"id": s.get("eta_seller_id") or "", "name": s.get("eta_seller_name") or "",
            "activityCode": s.get("eta_activity_code") or "",
            "address": {"branchID": s.get("eta_branch_id") or "1", "country": "EG",
                        "governate": s.get("eta_governate") or "", "regionCity": s.get("eta_region_city") or "",
                        "street": s.get("eta_street") or "", "buildingNumber": s.get("eta_building") or ""}}


def _inv_from_si(si):
    cust = {}
    if si.customer:
        cust = frappe.db.get_value("Customer", si.customer, ["customer_name", "customer_type", "tax_id"], as_dict=True) or {}
        cust = {"name": cust.get("customer_name") or si.customer,
                "type": "B" if cust.get("tax_id") else "P", "id": cust.get("tax_id") or ""}
    return {"number": si.name, "datetime_issued": si.posting_date.isoformat() + "T00:00:00Z" if hasattr(si.posting_date, "isoformat") else str(si.posting_date),
            "currency": si.currency, "is_return": bool(si.is_return),
            "lines": [{"itemId": r.item_code, "name": r.item_name or r.item_code, "qty": abs(flt(r.qty)),
                       "price": flt(r.price_list_rate) or flt(r.rate), "discount": flt(r.discount_amount) * abs(flt(r.qty))}
                      for r in si.items],
            "payments": [{"method": p.mode_of_payment, "amount": flt(p.amount)} for p in si.payments],
            "customer": cust}


def maybe_queue_receipt(si_name):
    """Called after a POS invoice submits. No-op when ETA is off or the invoice was not made by the POS."""
    if not eta_enabled():
        return None
    si = frappe.get_doc("Sales Invoice", si_name)
    if not si.get("orbit_txn_id"):
        return None
    if frappe.db.exists("POS ETA Receipt", {"sales_invoice": si_name}):
        return None
    try:
        doc = E.build_receipt_document(_inv_from_si(si), _seller())
    except E.EtaError as e:
        # a receipt that cannot even be built is queued as rejected so it is never silently lost
        rec = frappe.get_doc({"doctype": "POS ETA Receipt", "sales_invoice": si_name, "state": "rejected",
                              "environment": "build", "error": str(e)})
        rec.insert(ignore_permissions=True)
        return rec.name
    rec = frappe.get_doc({"doctype": "POS ETA Receipt", "sales_invoice": si_name, "receipt_uuid": doc["header"]["uuid"],
                          "state": "queued", "environment": (settings().get("eta_environment") or "Preprod"),
                          "receipt_json": json.dumps(doc, default=str)})
    rec.insert(ignore_permissions=True)
    return rec.name


@frappe.whitelist()
def eta_submit(name):
    """Sign and submit one queued receipt. Mock mode runs the whole flow against our mock built from
    the docs; Preprod/Prod need the client's ETA credentials and registration, so they refuse clearly."""
    require_pos_user()
    require("settings")
    rec = frappe.get_doc("POS ETA Receipt", name)
    if rec.state in ("submitted", "accepted"):
        frappe.throw(frappe._("This receipt was already submitted"))
    doc = frappe.parse_json(rec.receipt_json)
    env = settings().get("eta_environment") or "Preprod"
    if env != "mock":
        frappe.throw(frappe._("Live ETA submission needs the client's tax registration, a POS registered on pos.eta.gov.eg and the signing certificate. Configure those first."))
    signed = E.sign_document(doc, E.mock_signer)
    result = E.mock_submission([signed])
    rec.signed_json = json.dumps(signed, default=str)
    rec.submission_uuid = result["submissionUUID"]
    rec.submitted_at = now_datetime()
    if result["acceptedDocuments"]:
        rec.state = "accepted"
        rec.long_id = result["acceptedDocuments"][0]["longId"]
        rec.error = ""
    else:
        rec.state = "rejected"
        rec.error = result["rejectedDocuments"][0]["error"]["message"]
    rec.save(ignore_permissions=True)
    return _info(rec)


@frappe.whitelist()
def eta_submit_all():
    """Submit every queued receipt (used by the ETA screen and the scheduler)."""
    require_pos_user()
    require("settings")
    out = []
    for name in frappe.get_all("POS ETA Receipt", filters={"state": "queued"}, pluck="name"):
        try:
            out.append(eta_submit(name))
        except Exception as e:
            out.append({"name": name, "state": "error", "error": str(e)[:200]})
    return out


@frappe.whitelist()
def eta_list(state=None):
    require_pos_user()
    require("viewOtherShifts")
    filters = {}
    if state:
        filters["state"] = state
    return frappe.get_all("POS ETA Receipt", filters=filters, order_by="creation desc", limit=200,
                          fields=["name", "sales_invoice", "receipt_uuid", "state", "long_id", "error", "environment"])


@frappe.whitelist()
def eta_retry(name):
    """Requeue a rejected receipt (after the cause was fixed). Keeps the original UUID reference."""
    require_pos_user()
    require("settings")
    rec = frappe.get_doc("POS ETA Receipt", name)
    if rec.state != "rejected":
        frappe.throw(frappe._("Only a rejected receipt can be requeued"))
    rec.state = "queued"
    rec.error = ""
    rec.save(ignore_permissions=True)
    return _info(rec)


def _info(rec):
    return {"name": rec.name, "sales_invoice": rec.sales_invoice, "receipt_uuid": rec.receipt_uuid or "",
            "state": rec.state, "long_id": rec.long_id or "", "error": rec.error or "",
            "submission_uuid": rec.submission_uuid or ""}
