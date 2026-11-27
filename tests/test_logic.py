import unittest
from datetime import date, datetime
from orbit_pos.logic.promotions import apply_promotions, promo_active
from orbit_pos.logic.barcodes import make_ean13, valid_ean13, parse_scale_barcode, ean13_check_digit
from orbit_pos.logic.returns import return_allowed, refund_amount, cross_branch_allowed, credit_expiry, credit_expired, split_credit
from orbit_pos.logic.loyalty import points_earned, redeem_value
from orbit_pos.logic.offline import TxnRegistry, make_txn_id

B23 = {"id": "p1", "name": "buy 2 get 3", "type": "bxgy", "scope": {"type": "item", "value": "chips"},
       "params": {"buy": 2, "get": 3}}


def sale(qty, price=4.0, item="chips"):
    return [{"itemId": item, "qty": qty, "price": price}]


class Promo(unittest.TestCase):
    def free(self, qty):
        r = apply_promotions(sale(qty), [B23])
        return r["lines"][0]["promoDisc"] / 4.0

    def test_buy2_get3(self):
        # 3 free per complete group of 5 units
        self.assertEqual([self.free(q) for q in (1, 4, 5, 7, 10)], [0, 0, 3, 3, 6])

    def test_pooled_across_lines(self):
        r = apply_promotions([{"itemId": "chips", "qty": 3, "price": 4}, {"itemId": "chips", "qty": 2, "price": 4}], [B23])
        self.assertEqual(sum(l["promoDisc"] for l in r["lines"]), 12.0)

    def test_five_chips_total(self):
        self.assertEqual(apply_promotions(sale(5), [B23])["subtotal"], 8.0)

    def test_cheapest_free(self):
        p = {"name": "b1g1", "type": "bxgy", "params": {"buy": 1, "get": 1}}
        r = apply_promotions([{"itemId": "a", "qty": 1, "price": 10}, {"itemId": "b", "qty": 1, "price": 6}], [p])
        self.assertEqual(r["subtotal"], 10.0)

    def test_percent_and_amount(self):
        r = apply_promotions(sale(2, 10), [{"name": "x", "type": "percent", "params": {"percent": 10}}])
        self.assertEqual(r["subtotal"], 18.0)
        r = apply_promotions(sale(2, 10), [{"name": "y", "type": "amount", "params": {"amount": 3}}])
        self.assertEqual(r["subtotal"], 14.0)

    def test_best_non_stackable_wins_stackable_adds(self):
        ps = [{"name": "a", "type": "percent", "params": {"percent": 10}},
              {"name": "b", "type": "percent", "params": {"percent": 20}},
              {"name": "c", "type": "amount", "params": {"amount": 1}, "stackable": True}]
        r = apply_promotions(sale(1, 10), ps)
        self.assertEqual(r["subtotal"], 7.0)

    def test_manual_replaces_promo(self):
        l = sale(1, 10); l[0]["manualPct"] = 5
        r = apply_promotions(l, [{"name": "a", "type": "percent", "params": {"percent": 50}}])
        self.assertEqual(r["subtotal"], 9.5)

    def test_bundle(self):
        p = {"name": "3 for 20", "type": "bundle", "params": {"qty": 3, "price": 20}}
        self.assertEqual(apply_promotions(sale(3, 10), [p])["subtotal"], 20.0)
        self.assertEqual(apply_promotions(sale(7, 10), [p])["subtotal"], 20 * 2 + 10)

    def test_invoice_level(self):
        ps = [{"name": "inv", "type": "invoice_pct", "params": {"percent": 10, "minTotal": 100}}]
        self.assertEqual(apply_promotions(sale(1, 90), ps)["invoicePromoDisc"], 0)
        self.assertEqual(apply_promotions(sale(1, 200), ps)["invoicePromoDisc"], 20.0)

    def test_dates_and_days(self):
        p = {"start": "2026-11-01", "end": "2026-11-30"}
        self.assertTrue(promo_active(p, datetime(2026, 11, 25)))
        self.assertFalse(promo_active(p, datetime(2026, 12, 1)))
        wed = datetime(2026, 11, 25)  # Wednesday -> JS day 3
        self.assertTrue(promo_active({"days": [3]}, wed))
        self.assertFalse(promo_active({"days": [0, 6]}, wed))
        self.assertFalse(promo_active({"active": False}, wed))


class Barcodes(unittest.TestCase):
    def test_ean(self):
        self.assertEqual(ean13_check_digit("400638133393"), 1)  # known EAN-13 4006381333931
        c = make_ean13(1)
        self.assertTrue(valid_ean13(c) and c.startswith("200"))
        self.assertNotEqual(make_ean13(1), make_ean13(2))

    def test_scale(self):
        body = "21" + "00123" + "01250"
        code = body + str(ean13_check_digit(body))
        self.assertEqual(parse_scale_barcode(code), {"plu": "00123", "qty": 1.25})
        self.assertIsNone(parse_scale_barcode("2100123012509"))  # bad length/check


class Returns(unittest.TestCase):
    def test_window(self):
        t = date(2026, 11, 25)
        self.assertEqual(return_allowed("2026-11-20", t), (True, False))
        self.assertEqual(return_allowed("2026-11-11", t), (True, False))   # exactly 14 days
        self.assertEqual(return_allowed("2026-11-10", t), (False, True))
        self.assertEqual(return_allowed("2026-11-10", t, manager_approved=True), (True, True))

    def test_refund_prorata_no_cent_drift(self):
        a = refund_amount(10.00, 3, 1)
        b = refund_amount(10.00, 3, 1, already_returned_qty=1)
        c = refund_amount(10.00, 3, 1, already_returned_qty=2)
        self.assertEqual(round(a + b + c, 2), 10.00)
        with self.assertRaises(ValueError):
            refund_amount(10, 3, 4)

    def test_cross_branch(self):
        self.assertTrue(cross_branch_allowed("A", "A", False))
        self.assertFalse(cross_branch_allowed("A", "B", False))
        self.assertTrue(cross_branch_allowed("A", "B", True))


class Misc(unittest.TestCase):
    def test_loyalty(self):
        self.assertEqual(points_earned(95, 10), 9)
        self.assertEqual(redeem_value(100, 0.5, 30), 30)

    def test_offline_idempotent(self):
        r = TxnRegistry()
        t = make_txn_id("T1", "u", "s", 1, "2026-11-25T12:00:00")
        self.assertEqual(r.submit(t, "h"), "created")
        self.assertEqual(r.submit(t, "h"), "duplicate")
        self.assertEqual(r.submit(t, "other"), "conflict")


if __name__ == "__main__":
    unittest.main()


class ExchangeCredit(unittest.TestCase):
    def test_expiry_follows_the_setting(self):
        self.assertEqual(credit_expiry(date(2026, 1, 1), 14), date(2026, 1, 15))
        self.assertEqual(credit_expiry(date(2026, 1, 1), 7), date(2026, 1, 8))
        self.assertEqual(credit_expiry("2026-01-01", 30), date(2026, 1, 31))
        self.assertIsNone(credit_expiry(date(2026, 1, 1), 0))

    def test_expired_only_after_last_day(self):
        self.assertFalse(credit_expired(date(2026, 1, 15), date(2026, 1, 15)))
        self.assertTrue(credit_expired(date(2026, 1, 15), date(2026, 1, 16)))
        self.assertFalse(credit_expired(None, date(2030, 1, 1)))

    def test_split_credit(self):
        self.assertEqual(split_credit(10, 4), (4.0, 6.0))
        self.assertEqual(split_credit(10, 15), (10.0, 0.0))


from orbit_pos.logic.providers import (ProviderError, build_paymob_intention, parse_paymob_intention, parse_paymob_status,
                                       build_fawry_charge, verify_fawry_signature, parse_fawry_charge, parse_fawry_status,
                                       fawry_amount, piasters, create_attempt, mock_create)

SALE = {"ref": "TXN-1", "amount": 25.0, "currency": "EGP",
        "lines": [{"name": "Water", "qty": 5, "price": 5, "itemId": "Water"}],
        "customer": {"name": "Mona Ali", "phone": "01000000000", "email": "m@x.eg", "id": 7}}
PCFG = {"secret_key": "sk_test_x", "public_key": "pk_test_x", "payment_methods": [12345]}
FCFG = {"merchant_code": "MC1", "secure_key": "sekret"}


class Providers(unittest.TestCase):
    def test_piasters(self):
        self.assertEqual(piasters(25.0), 2500)
        self.assertEqual(piasters("0.01"), 1)

    def test_paymob_body(self):
        b = build_paymob_intention(SALE, PCFG)
        self.assertEqual(b["amount"], 2500)
        self.assertEqual(b["currency"], "EGP")
        self.assertEqual(b["payment_methods"], [12345])
        self.assertEqual(b["special_reference"], "TXN-1")
        self.assertEqual(b["items"][0]["amount"], 2500)
        self.assertEqual(b["billing_data"]["first_name"], "Mona")

    def test_paymob_needs_key_and_methods(self):
        with self.assertRaises(ProviderError):
            build_paymob_intention(SALE, {"payment_methods": [1]})
        with self.assertRaises(ProviderError):
            build_paymob_intention(SALE, {"secret_key": "x"})

    def test_paymob_parse_and_checkout_url(self):
        a = parse_paymob_intention({"id": 99, "client_secret": "cs1"}, PCFG)
        self.assertEqual(a["state"], "pending")
        self.assertEqual(a["ref"], "99")
        self.assertIn("publicKey=pk_test_x", a["checkout_url"])
        self.assertIn("clientSecret=cs1", a["checkout_url"])

    def test_paymob_status_map(self):
        self.assertEqual(parse_paymob_status({"success": True, "pending": False}), "paid")
        self.assertEqual(parse_paymob_status({"success": False, "pending": True}), "pending")
        self.assertEqual(parse_paymob_status({"success": False, "pending": False}), "failed")
        self.assertEqual(parse_paymob_status({"success": True, "pending": False, "is_refund": True}), "refunded")

    def test_fawry_body_and_signature(self):
        b = build_fawry_charge(SALE, FCFG)
        self.assertEqual(b["merchantCode"], "MC1")
        self.assertEqual(b["merchantRefNum"], "TXN-1")
        self.assertEqual(b["paymentMethod"], "PAYATFAWRY")
        self.assertEqual(b["amount"], "25.00")
        self.assertEqual(b["chargeItems"][0]["quantity"], 5)
        self.assertTrue(verify_fawry_signature(b, FCFG))
        b2 = dict(b, amount="26.00")
        self.assertFalse(verify_fawry_signature(b2, FCFG))

    def test_fawry_parse(self):
        a = parse_fawry_charge({"statusCode": 200, "referenceNumber": "R1"})
        self.assertEqual(a["state"], "pending")
        self.assertIn("R1", a["instructions"])
        with self.assertRaises(ProviderError):
            parse_fawry_charge({"statusCode": 400, "statusDescription": "bad"})

    def test_fawry_status_map(self):
        self.assertEqual(parse_fawry_status({"paymentStatus": "PAID"}), "paid")
        self.assertEqual(parse_fawry_status({"paymentStatus": "UNPAID"}), "pending")
        self.assertEqual(parse_fawry_status({"paymentStatus": "EXPIRED"}), "expired")
        self.assertEqual(parse_fawry_status({"paymentStatus": "REFUNDED"}), "refunded")

    def test_create_attempt_urls(self):
        r = create_attempt("paymob", SALE, PCFG)
        self.assertEqual(r["url"], "https://accept.paymob.com/v1/intention/")
        self.assertEqual(r["headers"]["Authorization"], "Token sk_test_x")
        r2 = create_attempt("fawry", SALE, FCFG, mode="test")
        self.assertIn("fawrystaging", r2["url"])
        r3 = create_attempt("fawry", SALE, FCFG, mode="live")
        self.assertIn("atfawry.com/ECommerceWeb", r3["url"])

    def test_mock_create(self):
        a = mock_create("paymob", build_paymob_intention(SALE, PCFG))
        self.assertEqual(a["state"], "pending")
        self.assertIn("publicKey=pk_mock", a["checkout_url"])
        a2 = mock_create("fawry", build_fawry_charge(SALE, FCFG))
        self.assertEqual(a2["state"], "pending")
        self.assertTrue(a2["ref"].startswith("FAWRY-"))
        with self.assertRaises(ProviderError):
            mock_create("aman", {})

    def test_fawry_amount(self):
        self.assertEqual(fawry_amount(25), "25.00")
        self.assertEqual(fawry_amount(0.1), "0.10")


from orbit_pos.logic.eta import (EtaError, build_receipt_document, build_item, compute_uuid, validate_receipt,
                                 sign_document, mock_signer, mock_submission, serialize_for_hash)

SELLER = {"id": "113317713", "name": "Orbit Demo Store", "activityCode": "4751",
          "address": {"branchID": "1", "country": "EG", "governate": "Cairo", "regionCity": "Nasr City",
                      "street": "10 Abbas El Akkad", "buildingNumber": "10"}}
INV = {"number": "POS-0001", "datetime_issued": "2026-11-27T10:00:00Z", "currency": "EGP",
       "lines": [{"itemId": "6223", "name": "Water", "qty": 5, "price": 5},
                 {"itemId": "6221", "name": "Chips", "qty": 2, "price": 4, "discount": 1}],
       "payments": [{"method": "Cash", "amount": 32}],
       "customer": {"name": "Mona Ali", "type": "P"}}


class Eta(unittest.TestCase):
    def test_document_shape(self):
        doc = build_receipt_document(INV, SELLER)
        self.assertEqual(doc["documentType"]["receiptType"], "s")
        self.assertEqual(doc["documentType"]["typeVersion"], "1.2")
        self.assertEqual(doc["header"]["receiptNumber"], "POS-0001")
        self.assertEqual(doc["totalSale"], 33.0)
        self.assertEqual(doc["netAmount"], 32.0)
        self.assertEqual(doc["paymentMethod"], "C")
        self.assertEqual(len(doc["header"]["uuid"]), 64)
        self.assertEqual(doc["itemData"][1]["itemsDiscount"], 1.0)
        self.assertEqual(doc["itemData"][1]["netTotal"], 7.0)

    def test_return_receipt(self):
        doc = build_receipt_document(dict(INV, is_return=True), SELLER)
        self.assertEqual(doc["documentType"]["receiptType"], "r")
        self.assertEqual(doc["documentType"]["receiptTypeBase"], "RR")

    def test_uuid_matches_content_and_ignores_uuid_field(self):
        doc = build_receipt_document(INV, SELLER)
        self.assertEqual(compute_uuid(doc), doc["header"]["uuid"])
        doc["header"]["receiptNumber"] = "POS-0002"
        self.assertNotEqual(compute_uuid(doc), doc["header"]["uuid"])   # tamper detected

    def test_validation_catches_missing(self):
        doc = build_receipt_document(INV, SELLER)
        self.assertEqual(validate_receipt(doc), [])
        bad = build_receipt_document(INV, SELLER)
        bad["seller"]["address"]["country"] = "US"
        self.assertTrue(any("country must be EG" in e for e in validate_receipt(bad)))
        with self.assertRaises(EtaError):
            build_receipt_document(dict(INV, lines=[]), SELLER)
        with self.assertRaises(EtaError):
            build_receipt_document(dict(INV, number=""), SELLER)

    def test_mixed_tender_payment_method(self):
        doc = build_receipt_document(dict(INV, payments=[{"method": "Cash"}, {"method": "Gift Card"}]), SELLER)
        self.assertEqual(doc["paymentMethod"], "C+GC")

    def test_mock_submission_accept_and_reject(self):
        good = sign_document(build_receipt_document(INV, SELLER), mock_signer)
        baddoc = build_receipt_document(INV, SELLER)
        baddoc["header"]["receiptNumber"] = ""                       # invalid: no number (and uuid now stale)
        bad = sign_document(baddoc, mock_signer)
        r = mock_submission([good, bad])
        self.assertEqual(len(r["submissionUUID"]), 64)
        self.assertEqual(len(r["acceptedDocuments"]), 1)
        self.assertEqual(len(r["rejectedDocuments"]), 1)
        self.assertIn("receiptNumber", r["rejectedDocuments"][0]["error"]["message"])
        self.assertTrue(r["acceptedDocuments"][0]["longId"].startswith("MOCK"))

    def test_serialization_skips_empty_and_uuid(self):
        s = serialize_for_hash({"a": "x", "uuid": "IGNORED", "b": "", "c": ["y"]})
        self.assertNotIn("IGNORED", s)
        self.assertIn('"X"', s)
        self.assertIn('"Y"', s)
