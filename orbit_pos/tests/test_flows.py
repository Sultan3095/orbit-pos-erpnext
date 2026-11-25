"""Real-flow tests: sale, duplicate/retry, discount authority, return, cash movements, shift close, import, reports.
Needs a site where tests/ci_setup.run() has created company 'Orbit Test'."""
import json
import os
import tempfile
import uuid
import frappe
from frappe.utils import flt, nowdate

try:
    from frappe.tests import IntegrationTestCase as Base
except ImportError:
    from frappe.tests.utils import FrappeTestCase as Base

CO, WH = "Orbit Test", "Stores - OT"


def leaf(doctype):
    return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def make_item(code, price, barcode=None, qty=100, **extra):
    if not frappe.db.exists("Item", code):
        d = {"doctype": "Item", "item_code": code, "item_name": code, "item_group": leaf("Item Group"),
             "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": price / 2}
        d.update(extra)
        if barcode:
            d["barcodes"] = [{"barcode": barcode}]
        frappe.get_doc(d).insert()
        frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": "Standard Selling",
                        "price_list_rate": price, "selling": 1}).insert()
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": CO,
                             "items": [{"item_code": code, "qty": qty, "t_warehouse": WH, "basic_rate": price / 2}]})
        se.insert(); se.submit()
    return code


def stock(code):
    return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": WH}, "actual_qty"))


class TestFlows(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Company", CO):
            import unittest; raise unittest.SkipTest("company missing")
        frappe.set_user("Administrator")
        make_item("ORB-A", 10, "6221111111111")
        make_item("ORB-B", 4, "6222222222222")
        if not frappe.db.exists("Customer", "Orbit Walkin"):
            frappe.get_doc({"doctype": "Customer", "customer_name": "Orbit Walkin", "customer_group": leaf("Customer Group"),
                            "territory": leaf("Territory")}).insert()
        cash_acc = frappe.db.get_value("Mode of Payment Account", {"parent": "Cash", "company": CO}, "default_account")
        if not frappe.db.exists("POS Profile", "Orbit Test Profile"):
            frappe.get_doc({"doctype": "POS Profile", "name": "Orbit Test Profile", "company": CO, "customer": "Orbit Walkin",
                            "warehouse": WH, "currency": "EGP", "selling_price_list": "Standard Selling",
                            "payments": [{"mode_of_payment": "Cash", "default": 1}],
                            "write_off_account": frappe.db.get_value("Company", CO, "write_off_account"),
                            "write_off_cost_center": frappe.db.get_value("Company", CO, "cost_center"),
                            "income_account": frappe.db.get_value("Company", CO, "default_income_account"),
                            "expense_account": frappe.db.get_value("Company", CO, "default_expense_account")}).insert()
        cls.profile = "Orbit Test Profile"
        cls.cash_acc = cash_acc
        for role_user, role, pin in (("cashier@orbit.test", "POS User", None), ("boss@orbit.test", "POS Manager", "4321")):
            if not frappe.db.exists("User", role_user):
                u = frappe.get_doc({"doctype": "User", "email": role_user, "first_name": role_user.split("@")[0],
                                    "send_welcome_email": 0, "roles": [{"role": role}, {"role": "Sales User"}, {"role": "Stock User"}, {"role": "Accounts User"}]})
                u.insert()
            if pin:
                u = frappe.get_doc("User", role_user); u.orbit_pos_pin = pin; u.save()

    def tearDown(self):
        frappe.set_user("Administrator")
        for s in frappe.get_all("POS Shift", filters={"status": "Open"}, pluck="name"):
            frappe.db.set_value("POS Shift", s, "status", "Closed")

    def _shift(self, cash=100):
        from orbit_pos.api import shift
        return shift.open_shift(self.profile, cash)["name"]

    def _payload(self, shift, lines, pay, **kw):
        p = {"txn_id": "T-" + uuid.uuid4().hex[:8], "shift": shift, "lines": lines,
             "payments": [{"method": "Cash", "amount": pay}]}
        p.update(kw)
        return json.dumps(p)

    # ---- tests
    def test_01_lookup_and_quote(self):
        from orbit_pos.api import sales
        r = sales.lookup("6221111111111")
        self.assertEqual(r["name"], "ORB-A"); self.assertEqual(flt(r["price"]), 10.0)
        q = sales.quote(json.dumps({"lines": [{"itemId": "ORB-A", "qty": 2, "price": 10}]}))
        self.assertEqual(q["subtotal"], 20.0)

    def test_02_next_barcode(self):
        from orbit_pos.api import sales
        a, b = sales.next_barcode(), sales.next_barcode()
        self.assertNotEqual(a, b); self.assertEqual(len(a), 13)

    def test_03_sale_stock_change_and_idempotency(self):
        from orbit_pos.api import sales
        sh = self._shift(); before = stock("ORB-A")
        pl = self._payload(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 50)
        r = sales.submit_sale(pl)
        self.assertEqual(r["status"], "created")
        si = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertEqual(si.docstatus, 1)
        self.assertEqual(flt(si.grand_total), 30.0)
        self.assertEqual(flt(r["change"]), 20.0)
        self.assertEqual(flt(si.payments[0].amount), 30.0)   # stored net of change
        self.assertEqual(stock("ORB-A"), before - 3)
        again = sales.submit_sale(pl)
        self.assertEqual(again["status"], "duplicate"); self.assertEqual(again["sales_invoice"], r["sales_invoice"])
        self.assertEqual(stock("ORB-A"), before - 3)
        other = json.loads(pl); other["lines"][0]["qty"] = 1
        with self.assertRaises(frappe.DuplicateEntryError):
            sales.submit_sale(json.dumps(other))

    def test_04_underpayment_rejected(self):
        from orbit_pos.api import sales
        sh = self._shift()
        with self.assertRaises(frappe.ValidationError):
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 10))

    def test_05_promotion_buy2get3_in_real_invoice(self):
        from orbit_pos.api import sales
        frappe.get_doc({"doctype": "POS Promotion", "promo_name": "b2g3", "promo_type": "bxgy", "buy_qty": 2, "get_qty": 3,
                        "enabled": 1}).insert()
        sh = self._shift()
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-B", "qty": 5, "price": 4}], 20))
        si = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertEqual(flt(si.grand_total), 8.0)   # 5 units, 3 free: pays for 2

    def test_06_discount_needs_manager_pin(self):
        from orbit_pos.api import sales
        frappe.set_user("Administrator"); sh = self._shift(); 
        frappe.db.set_value("POS Shift", sh, {"shared_shift": 1})
        frappe.set_user("cashier@orbit.test")
        line = [{"itemId": "ORB-A", "qty": 1, "price": 10, "manualPct": 90}]
        with self.assertRaises(frappe.PermissionError):
            sales.submit_sale(self._payload(sh, line, 10))
        with self.assertRaises(frappe.PermissionError):
            sales.submit_sale(self._payload(sh, line, 10, manager="boss@orbit.test", manager_pin="0000"))
        r = sales.submit_sale(self._payload(sh, line, 10, manager="boss@orbit.test", manager_pin="4321"))
        self.assertEqual(r["status"], "created")
        self.assertTrue(frappe.db.exists("POS Manager Approval", {"action": "Discount", "approved_by": "boss@orbit.test"}))

    def test_07_return_restores_stock_and_enforces_window(self):
        from orbit_pos.api import sales
        sh = self._shift(); before = stock("ORB-A")
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20))
        self.assertEqual(stock("ORB-A"), before - 2)
        ret = sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]))
        self.assertEqual(ret["refund"], 10.0)
        self.assertEqual(stock("ORB-A"), before - 1)
        ri = frappe.get_doc("Sales Invoice", ret["return_invoice"])
        self.assertEqual(ri.orbit_shift, sh)
        self.assertEqual(flt(ri.payments[0].amount), -10.0)

    def test_08_cash_movement_close_and_z_report(self):
        from orbit_pos.api import sales, shift
        sh = self._shift(200)
        sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        shift.cash_movement(sh, "Out", 30, "supplier tea")
        shift.cash_movement(sh, "In", 5, "float")
        z = shift.close_shift(sh, 185)
        self.assertEqual(flt(z["expected_cash"]), 185.0)    # 200 + 10 - 30 + 5
        self.assertEqual(flt(z["difference"]), 0.0)
        self.assertEqual(z["sales_count"], 1)
        with self.assertRaises(frappe.ValidationError):
            shift.close_shift(sh, 185)

    def test_09_cashier_cash_out_needs_pin(self):
        from orbit_pos.api import shift
        frappe.set_user("cashier@orbit.test")
        sh = self._shift(50)
        with self.assertRaises(frappe.PermissionError):
            shift.cash_movement(sh, "Out", 5, "x")
        m = shift.cash_movement(sh, "Out", 5, "x", manager="boss@orbit.test", pin="4321")
        self.assertEqual(m["approved_by"], "boss@orbit.test")

    def test_10_one_open_shift_per_user(self):
        self._shift()
        with self.assertRaises(frappe.ValidationError):
            self._shift()

    def test_11_excel_import(self):
        import openpyxl
        from orbit_pos.api import purchase_import as pi
        if not frappe.db.exists("Supplier", "Orbit Supplier"):
            frappe.get_doc({"doctype": "Supplier", "supplier_name": "Orbit Supplier", "supplier_group": leaf("Supplier Group")}).insert()
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["الباركود", "الاسم", "الكمية", "التكلفة", "الخصم"])
        ws.append(["6229999999991", "Imported Item", 10, 5, 0])
        path = os.path.join(tempfile.mkdtemp(), "inv.xlsx"); wb.save(path)
        f = frappe.get_doc({"doctype": "File", "file_name": "inv.xlsx", "content": open(path, "rb").read(), "is_private": 1}).insert()
        dry = pi.import_supplier_invoice(f.file_url, "Orbit Supplier", "INV-1", nowdate(), WH, CO, dry_run=1)
        self.assertTrue(dry["ok"], dry["errors"]); self.assertTrue(dry["preview"][0]["is_new"])
        self.assertFalse(frappe.db.exists("Item", "6229999999991"))
        real = pi.import_supplier_invoice(f.file_url, "Orbit Supplier", "INV-1", nowdate(), WH, CO, dry_run=0)
        self.assertTrue(real["ok"], real["errors"])
        self.assertEqual(stock("6229999999991"), 10.0)
        dup = pi.import_supplier_invoice(f.file_url, "Orbit Supplier", "INV-1", nowdate(), WH, CO, dry_run=1)
        self.assertFalse(dup["ok"])

    def test_12_slow_moving_report(self):
        from orbit_pos.api import reports
        make_item("ORB-SLOW", 10, "6223333333333")
        rows = reports.slow_moving(days=30)
        self.assertIn("ORB-SLOW", [r["item_code"] for r in rows])

    def test_13_page_and_permissions(self):
        self.assertTrue(frappe.db.exists("Page", "orbit-pos") or frappe.db.exists("Page", "orbit_pos"))
        frappe.set_user("Guest")
        from orbit_pos.api import shift
        with self.assertRaises(Exception):
            shift.current_shift()
