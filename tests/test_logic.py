import unittest
from datetime import date, datetime
from orbit_pos.logic.promotions import apply_promotions, promo_active
from orbit_pos.logic.barcodes import make_ean13, valid_ean13, parse_scale_barcode, ean13_check_digit
from orbit_pos.logic.returns import return_allowed, refund_amount, cross_branch_allowed
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
