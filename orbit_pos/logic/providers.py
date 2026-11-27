"""Payment provider layer, pure logic (no Frappe imports, unit-testable anywhere).

One shape for every provider the POS can tender with:
  create -> {provider, ref, state, amount, currency, instructions, checkout_url}
  status updates move the attempt through STATES below.

Providers: "paymob" and "fawry". Every provider has three modes:
  mock - our own simulation built from the official docs (no network, deterministic)
  test - the provider's own test/staging environment with test credentials
  live - the provider's production environment with the client's credentials
Only the base URL and the keys change between test and live; the payloads are the same.

Grounding (built from the docs, not from a live account):
- Paymob Intention API: POST {base}/v1/intention/ with "Authorization: Token <secret key>".
  Amounts are in the smallest currency unit (piasters). Response carries id and client_secret;
  the customer pays on the unified checkout page {checkout_base}?publicKey=..&clientSecret=..
  https://developers.paymob.com/paymob-docs/api-reference/intention-api/create-intention
- Fawry charge API: POST {base}/ECommerceWeb/Fawry/payments/charge with merchantCode,
  merchantRefNum, customer details, paymentMethod, currencyCode, amount, chargeItems and a
  SHA-256 signature over merchantCode+merchantRefNum+customerProfileId+paymentMethod+amount+secureKey.
  A PAYATFAWRY payment returns a reference number the customer pays at a Fawry point.
  https://developer.fawrystaging.com/docs/server-apis/create-payment-refno-apis
"""
import hashlib
import json

STATES = ("pending", "paid", "failed", "expired", "refunded")
TERMINAL = ("paid", "failed", "expired", "refunded")

PAYMOB_BASE = "https://accept.paymob.com"
PAYMOB_CHECKOUT = "https://eg.checkout.paymob.com/"
FAWRY_BASE_LIVE = "https://www.atfawry.com"
FAWRY_BASE_TEST = "https://atfawry.fawrystaging.com"

PROVIDERS = ("paymob", "fawry")


class ProviderError(ValueError):
    """Bad config or a response that does not look like the provider's documented shape."""


def _check_state(state):
    if state not in STATES:
        raise ProviderError("unknown payment state %r" % (state,))
    return state


# ---------------- Paymob ----------------

def piasters(amount):
    """Pounds -> piasters, rounded half up. Paymob amounts are integers in the smallest unit."""
    return int(round(float(amount) * 100))


def build_paymob_intention(sale, cfg):
    """Request body for POST {base}/v1/intention/. `sale`: {ref, amount, currency, lines, customer}.
    cfg: {secret_key, payment_methods, notification_url?, redirection_url?}."""
    if not cfg.get("secret_key"):
        raise ProviderError("Paymob secret key is not configured")
    methods = cfg.get("payment_methods")
    if not methods:
        raise ProviderError("Paymob needs at least one integration id in payment_methods")
    amount = piasters(sale["amount"])
    if amount <= 0:
        raise ProviderError("Paymob amount must be more than zero")
    cust = sale.get("customer") or {}
    name = (cust.get("name") or "POS Customer").split(" ", 1)
    body = {
        "amount": amount,
        "currency": sale.get("currency") or "EGP",
        "payment_methods": list(methods),
        "items": [
            {"name": l["name"], "amount": piasters(l["price"] * l["qty"]),
             "description": l.get("description") or l["name"], "quantity": int(l["qty"])}
            for l in sale.get("lines") or []
        ],
        "billing_data": {
            "first_name": name[0], "last_name": name[1] if len(name) > 1 else "-",
            "phone_number": cust.get("phone") or "NA", "email": cust.get("email") or "NA",
            "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA",
            "shipping_method": "NA", "postal_code": "NA", "city": "NA",
            "country": "NA", "state": "NA",
        },
        "special_reference": sale["ref"],
        "extras": {"orbit_txn_id": sale["ref"]},
    }
    if cfg.get("notification_url"):
        body["notification_url"] = cfg["notification_url"]
    if cfg.get("redirection_url"):
        body["redirection_url"] = cfg["redirection_url"]
    return body


def parse_paymob_intention(resp, cfg):
    """Create-intention response -> our attempt shape. Checkout URL needs the public key."""
    if not isinstance(resp, dict) or not resp.get("id") or not resp.get("client_secret"):
        raise ProviderError("Paymob response has no id/client_secret")
    if not cfg.get("public_key"):
        raise ProviderError("Paymob public key is not configured")
    return {"provider": "paymob", "ref": str(resp["id"]), "state": "pending",
            "client_secret": resp["client_secret"],
            "checkout_url": "%s?publicKey=%s&clientSecret=%s" % (PAYMOB_CHECKOUT, cfg["public_key"], resp["client_secret"])}


def parse_paymob_status(resp):
    """Transaction inquiry / callback -> one of our states."""
    success = bool(resp.get("success"))
    pending = bool(resp.get("pending"))
    is_refund = bool(resp.get("is_refund")) or (resp.get("order") or {}).get("is_refund", False) and success
    if success and is_refund:
        return "refunded"
    if success and not pending:
        return "paid"
    if pending:
        return "pending"
    if resp.get("is_voided") or resp.get("is_refund"):
        return "refunded"
    return "failed"


# ---------------- Fawry ----------------

def fawry_amount(amount):
    """Fawry takes a decimal with exactly 2 places."""
    return "%.2f" % round(float(amount) + 1e-9, 2)


def fawry_signature(cfg, merchant_ref_num, customer_profile_id, payment_method, amount):
    """SHA-256 over merchantCode + merchantRefNum + customerProfileId + paymentMethod + amount + secureKey."""
    for k in ("merchant_code", "secure_key"):
        if not cfg.get(k):
            raise ProviderError("Fawry %s is not configured" % k.replace("_", " "))
    raw = "%s%s%s%s%s%s" % (cfg["merchant_code"], merchant_ref_num, customer_profile_id or "",
                            payment_method, amount, cfg["secure_key"])
    return hashlib.sha256(raw.encode()).hexdigest()


def build_fawry_charge(sale, cfg, payment_method="PAYATFAWRY"):
    """Request body for POST {base}/ECommerceWeb/Fawry/payments/charge."""
    ref = sale["ref"]
    cust = sale.get("customer") or {}
    profile_id = str(cust.get("id") or "")
    amount = fawry_amount(sale["amount"])
    return {
        "merchantCode": cfg.get("merchant_code") or "",
        "merchantRefNum": ref,
        "customerProfileId": profile_id,
        "customerName": cust.get("name") or "POS Customer",
        "customerMobile": cust.get("phone") or "",
        "customerEmail": cust.get("email") or "",
        "paymentMethod": payment_method,
        "currencyCode": sale.get("currency") or "EGP",
        "amount": amount,
        "chargeItems": [
            {"itemId": str(l.get("itemId") or i), "description": l["name"],
             "price": fawry_amount(l["price"]), "quantity": int(l["qty"])}
            for i, l in enumerate(sale.get("lines") or [])
        ],
        "signature": fawry_signature(cfg, ref, profile_id, payment_method, amount),
    }


def verify_fawry_signature(body, cfg):
    """Recompute the signature of a charge body; True when it matches."""
    return fawry_signature(cfg, body.get("merchantRefNum", ""), body.get("customerProfileId", ""),
                           body.get("paymentMethod", ""), body.get("amount", "")) == body.get("signature")


def parse_fawry_charge(resp):
    """Charge response -> our attempt shape. 200/201 with a referenceNumber means the payment is pending."""
    if not isinstance(resp, dict):
        raise ProviderError("Fawry response is not an object")
    code = resp.get("statusCode")
    ref = resp.get("referenceNumber") or resp.get("merchantRefNumber") or resp.get("merchantRefNum")
    if code in (200, 201) and ref:
        return {"provider": "fawry", "ref": str(ref), "state": "pending",
                "instructions": "pay at a Fawry point with reference %s" % ref}
    raise ProviderError("Fawry refused: %s %s" % (code, resp.get("statusDescription") or resp.get("statusDetails") or ""))


def parse_fawry_status(resp):
    """Payment status/callback -> one of our states. Fawry statuses: PAID, UNPAID, EXPIRED, REFUNDED."""
    s = str(resp.get("paymentStatus") or resp.get("status") or "").upper()
    return {"PAID": "paid", "UNPAID": "pending", "EXPIRED": "expired",
            "REFUNDED": "refunded", "FAILED": "failed", "CANCELLED": "failed"}.get(s, "pending")


# ---------------- shared ----------------

def create_attempt(provider, sale, cfg, mode="mock"):
    """One entry point: returns (request_body, parse) for the provider, so the caller (api layer)
    can send it over HTTP (test/live) or hand it to the mock."""
    if provider == "paymob":
        body = build_paymob_intention(sale, cfg)
        url = PAYMOB_BASE + "/v1/intention/"
        headers = {"Authorization": "Token " + cfg["secret_key"], "Content-Type": "application/json"}
        return {"url": url, "headers": headers, "body": body, "parse": lambda r: parse_paymob_intention(r, cfg)}
    if provider == "fawry":
        body = build_fawry_charge(sale, cfg)
        base = FAWRY_BASE_TEST if mode == "test" else FAWRY_BASE_LIVE
        return {"url": base + "/ECommerceWeb/Fawry/payments/charge",
                "headers": {"Content-Type": "application/json"}, "body": body,
                "parse": parse_fawry_charge}
    raise ProviderError("unknown provider %r" % (provider,))


def mock_create(provider, request_body):
    """Our mock, built from the docs: behaves like the provider's documented happy path.
    Deterministic refs so tests and CI are stable."""
    if provider == "paymob":
        ident = int(hashlib.sha256(json.dumps(request_body, sort_keys=True).encode()).hexdigest()[:12], 16)
        secret = "cli_mock_%s" % request_body.get("special_reference", "x")
        return parse_paymob_intention({"id": ident, "client_secret": secret}, {"public_key": "pk_mock"})
    if provider == "fawry":
        ref = "FAWRY-" + hashlib.sha256(request_body["merchantRefNum"].encode()).hexdigest()[:10].upper()
        return parse_fawry_charge({"statusCode": 200, "referenceNumber": ref,
                                   "merchantRefNumber": request_body["merchantRefNum"]})
    raise ProviderError("unknown provider %r" % (provider,))
