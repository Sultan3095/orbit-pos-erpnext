"""ETA e-receipt (Egyptian Tax Authority) document logic, pure (no Frappe imports).

Builds a Receipt v1.2 document from an invoice-shaped dict, computes the document UUID as
SHA-256 over the serialized content (excluding the UUID itself, per the ETA core validator),
validates the mandatory fields, and signs through a pluggable signer.

Grounding (docs, not a live account):
- Receipt v1.2 structure: https://sdk.invoicing.eta.gov.eg/documents/receipt-v1-2/ and
  https://sdk.invoicing.eta.gov.eg/documents/retail-receipt-v1-2/ (header, documentType,
  seller, buyer, itemData, totals).
- UUID is a 64-char hash of the serialized receipt content excluding the UUID:
  https://sdk.invoicing.eta.gov.eg/receiptissuancefaq/ (core fields validator, rule 22).
- Submit one or more signed documents, results by callback or polling:
  https://sdk.invoicing.eta.gov.eg/ereceiptapi/02-submit-receipt/ and
  https://sdk.invoicing.eta.gov.eg/integrationpractices/
- The exact ETA serialization format is defined in their SDK; serialize_for_hash() below is our
  implementation of the documented pattern (recursive, UPPERCASE keys, values concatenated in
  structure order, UUID excluded). The mock validator re-derives the UUID with the same function,
  so the flow is proven end to end against our mock; the client's ETA onboarding still has to
  confirm the byte-exact format against the official SDK before go-live.
"""
import hashlib
import json

TYPE_VERSION = "1.2"
REQUIRED_SELLER = ("id", "name", "address")
REQUIRED_ADDRESS = ("branchID", "country", "governate", "regionCity", "street")


class EtaError(ValueError):
    pass


def _money(x):
    return round(float(x) + 1e-9, 5)


def build_item(line, currency="EGP"):
    """One invoice line -> ETA itemData entry."""
    qty = float(line["qty"])
    price = _money(line["price"])
    total_sale = _money(qty * price)
    disc = _money(line.get("discount") or 0)
    net = _money(total_sale - disc)
    return {
        "internalCode": str(line.get("itemId") or ""),
        "description": str(line.get("name") or line.get("itemId") or ""),
        "itemType": "GS1",                         # barcoded retail goods
        "itemCode": str(line.get("itemId") or ""),
        "unitType": str(line.get("unit") or "EA"),
        "quantity": qty,
        "unitSalePrice": price,
        "totalSale": total_sale,
        "total": net,
        "valueDifference": 0.0,
        "totalTaxableFees": 0.0,
        "netTotal": net,
        "itemsDiscount": disc,
        "unitValue": {"currencySold": currency, "amountEGP": price, "amountSold": price,
                      "currencyExchangeRate": 1.0},
    }


def build_receipt_document(inv, seller, prev_uuid=None, ref_old_uuid=None):
    """inv: {number, datetime_issued (UTC ISO), currency, lines, payments, is_return, customer}.
    seller: {id (tax registration), name, address {branchID, country, governate, regionCity, street, ...},
             activityCode?}. Returns the full Receipt v1.2 document (uuid filled in)."""
    if not inv.get("number"):
        raise EtaError("invoice has no receipt number")
    if not inv.get("datetime_issued"):
        raise EtaError("invoice has no issuance time")
    lines = [build_item(l, inv.get("currency") or "EGP") for l in inv.get("lines") or []]
    if not lines:
        raise EtaError("invoice has no lines")
    doc = {
        "header": {
            "dateTimeIssued": inv["datetime_issued"],
            "receiptNumber": str(inv["number"]),
            "uuid": "",
            "previousUUID": prev_uuid or "",
            "referenceOldUUID": ref_old_uuid or "",
            "currency": inv.get("currency") or "EGP",
            "exchangeRate": 1.0,
            "sOrderNameCode": "",
            "orderdeliveryMode": "FC",
            "grossWeight": 0.0,
            "netWeight": 0.0,
        },
        "documentType": {
            "receiptTypeCategory": "Receipt",
            "receiptTypeBase": "RR" if inv.get("is_return") else "SR",
            "receiptType": "r" if inv.get("is_return") else "s",
            "receiptTypeName": "PS" if inv.get("is_return") else "S",
            "typeVersion": TYPE_VERSION,
        },
        "seller": dict(seller),
        "buyer": _buyer(inv.get("customer")),
        "itemData": lines,
        "totalSale": _money(sum(l["totalSale"] for l in lines)),
        "totalTaxableFees": 0.0,
        "netAmount": _money(sum(l["netTotal"] for l in lines)),
        "paymentMethod": _payment_method(inv.get("payments")),
        "adjustment": 0.0,
    }
    doc["header"]["uuid"] = compute_uuid(doc)
    return doc


def _buyer(customer):
    """ETA buyer types: B business (tax id), P person (national id), F foreigner. Walk-in: P with no id."""
    c = customer or {}
    addr = c.get("address") or {}
    return {
        "type": c.get("type") or "P",
        "id": str(c.get("id") or ""),
        "name": str(c.get("name") or ""),
        "address": {"country": addr.get("country") or "EG",
                    "governate": addr.get("governate") or "",
                    "regionCity": addr.get("regionCity") or "",
                    "street": addr.get("street") or "",
                    "buildingNumber": addr.get("buildingNumber") or ""},
    }


def _payment_method(payments):
    """ETA paymentMethod codes: C cash, CC credit card, etc. Mixed tenders join with '+'."""
    codes = {"Cash": "C", "Credit Card": "CC", "Gift Card": "GC", "Exchange Credit": "C",
             "paymob": "CC", "fawry": "CC"}
    seen = []
    for p in payments or []:
        code = codes.get(p.get("method"), "O")
        if code not in seen:
            seen.append(code)
    return "+".join(seen) if seen else "C"


# ---------------- serialization and UUID ----------------

def serialize_for_hash(node):
    """Canonical serialization for hashing: every key UPPERCASE, every value appended in structure
    order, empty values and the UUID itself skipped. Strings quoted. Our implementation of the
    documented ETA pattern; the mock validator uses the same function."""
    if isinstance(node, dict):
        out = []
        for k in sorted(node.keys()):
            if k.lower() == "uuid":
                continue
            v = node[k]
            if v in (None, "", [], {}):
                continue
            out.append(k.upper())
            out.append(serialize_for_hash(v))
        return "".join(out)
    if isinstance(node, list):
        return "".join(serialize_for_hash(v) for v in node if v not in (None, "", [], {}))
    if isinstance(node, str):
        return '"%s"' % node.upper()
    if isinstance(node, float):
        return '"%s"' % ("%g" % node)
    return '"%s"' % node


def compute_uuid(doc):
    """SHA-256 hex of the serialized document with the UUID field excluded (ETA core rule 22)."""
    return hashlib.sha256(serialize_for_hash(doc).encode()).hexdigest()


# ---------------- validation and mock submission ----------------

def validate_receipt(doc):
    """Mandatory-field validation, mirroring the documented core validator. Returns a list of errors."""
    errors = []
    h = doc.get("header") or {}
    if not h.get("receiptNumber"):
        errors.append("receiptNumber is mandatory")
    if not h.get("dateTimeIssued"):
        errors.append("dateTimeIssued is mandatory")
    if h.get("referenceOldUUID") and h.get("referenceOldUUID") == h.get("uuid"):
        errors.append("ReferenceOldUUID cannot be equal to the UUID")
    if not h.get("uuid") or len(h["uuid"]) != 64:
        errors.append("uuid must be a 64-character hash")
    elif compute_uuid(doc) != h["uuid"]:
        errors.append("uuid does not match the serialized content")
    s = doc.get("seller") or {}
    for k in REQUIRED_SELLER:
        if not s.get(k):
            errors.append("seller.%s is mandatory" % k)
    addr = s.get("address") or {}
    for k in REQUIRED_ADDRESS:
        if not addr.get(k):
            errors.append("seller.address.%s is mandatory" % k)
    if addr.get("country") != "EG":
        errors.append("seller.address.country must be EG for an internal issuer")
    if not doc.get("itemData"):
        errors.append("itemData must not be empty")
    for i, it in enumerate(doc.get("itemData") or []):
        for k in ("internalCode", "description", "itemCode", "unitType", "quantity", "unitSalePrice"):
            if it.get(k) in (None, ""):
                errors.append("itemData[%d].%s is mandatory" % (i, k))
    if doc.get("documentType", {}).get("receiptType") not in ("s", "r"):
        errors.append("documentType.receiptType must be 's' or 'r'")
    return errors


def sign_document(doc, signer):
    """Attach the signature block through a pluggable signer (the client's token/certificate later,
    the mock signer in mock mode). Returns a signed-document envelope for submission."""
    return {"document": doc, "signatures": [signer(doc)]}


def mock_signer(doc):
    """Mock signer: proves the plumbing, not a real ETA signature. Clearly marked."""
    return {"signatureType": "MOCK", "signedBy": "orbit-mock-signer",
            "value": hashlib.sha256(("MOCK" + doc["header"]["uuid"]).encode()).hexdigest()}


def mock_submission(signed_documents):
    """Mock of the submit-receipt API, built from the docs: validates every document and returns
    accepted/rejected per document with a submission UUID, exactly the documented response shape."""
    accepted, rejected = [], []
    for env in signed_documents:
        doc = env.get("document") or {}
        uuid = (doc.get("header") or {}).get("uuid", "")
        errors = validate_receipt(doc)
        if not env.get("signatures"):
            errors.append("at least one signature is mandatory")
        if errors:
            rejected.append({"target": uuid, "error": {"code": "ValidationError", "message": "; ".join(errors),
                                                       "details": [{"code": "CFV", "message": e, "target": "document"} for e in errors]}})
        else:
            accepted.append({"uuid": uuid,
                             "longId": "MOCK" + uuid[:26].upper(),
                             "internalId": "MOCK-" + uuid[:12].upper()})
    return {"submissionUUID": hashlib.sha256(
        json.dumps([a["uuid"] for a in accepted] + [r["target"] for r in rejected]).encode()).hexdigest(),
            "acceptedDocuments": accepted, "rejectedDocuments": rejected}
