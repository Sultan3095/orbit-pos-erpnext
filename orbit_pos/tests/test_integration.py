"""Runs inside a real bench (bench --site test_site run-tests --app orbit_pos). Not runnable without Frappe."""
import frappe

try:                                    # v16
    from frappe.tests import IntegrationTestCase as Base
except ImportError:                     # v15
    from frappe.tests.utils import FrappeTestCase as Base


class TestOrbitPOS(Base):
    def test_promotion_engine_roundtrip(self):
        promo = frappe.get_doc({"doctype": "POS Promotion", "promo_name": "buy 2 get 3", "promo_type": "bxgy",
                                "buy_qty": 2, "get_qty": 3}).insert()
        from orbit_pos.logic.promotions import apply_promotions
        r = apply_promotions([{"itemId": "x", "qty": 5, "price": 4}], [promo.to_engine()])
        self.assertEqual(r["subtotal"], 8.0)

    def test_settings_defaults(self):
        s = frappe.get_single("Orbit POS Settings")
        self.assertEqual(int(s.return_window_days), 14)
        self.assertFalse(int(s.allow_cross_branch_returns))

    def test_roles_installed(self):
        self.assertTrue(frappe.db.exists("Role", "POS Manager"))
        self.assertTrue(frappe.db.exists("Role", "POS User"))

    def test_one_open_shift_per_user(self):
        profile = frappe.get_all("POS Profile", limit=1, pluck="name")
        if not profile:
            self.skipTest("needs a POS Profile in the test site")
        a = frappe.get_doc({"doctype": "POS Shift", "user": "Administrator", "pos_profile": profile[0], "status": "Open"}).insert()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "POS Shift", "user": "Administrator", "pos_profile": profile[0], "status": "Open"}).insert()
        a.status = "Closed"; a.save()
