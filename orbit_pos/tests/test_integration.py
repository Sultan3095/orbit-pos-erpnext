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

    def test_promotion_scope_required(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "POS Promotion", "promo_name": "no item", "promo_type": "percent", "percent": 10,
                            "scope_type": "Item"}).insert()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": "POS Promotion", "promo_name": "no group", "promo_type": "percent", "percent": 10,
                            "scope_type": "Item Group"}).insert()

    def test_promotion_on_parent_group_covers_sub_groups(self):
        for name, parent, is_group in (("Orbit Promo Parent", "All Item Groups", 1), ("Orbit Promo Child", "Orbit Promo Parent", 0)):
            if not frappe.db.exists("Item Group", name):
                frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent, "is_group": is_group}).insert()
        promo = frappe.get_doc({"doctype": "POS Promotion", "promo_name": "parent group 10%", "promo_type": "percent", "percent": 10,
                                "scope_type": "Item Group", "scope_item_group": "Orbit Promo Parent"}).insert()
        from orbit_pos.logic.promotions import apply_promotions
        lines = [{"itemId": "a", "group": "Orbit Promo Child", "qty": 1, "price": 100},
                 {"itemId": "b", "group": "Some Other Group", "qty": 1, "price": 100}]
        r = apply_promotions(lines, [promo.to_engine()])
        self.assertEqual(r["lines"][0]["promoDisc"], 10.0)    # sub-group is covered
        self.assertEqual(r["lines"][1]["promoDisc"], 0)       # unrelated group is not

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
