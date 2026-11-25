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
        sh = self._shift(500)
        small = shift.cash_movement(sh, "Out", 50, "bags from the supermarket")   # within the default 200 limit
        self.assertFalse(small.get("approved_by"))
        with self.assertRaises(frappe.PermissionError):
            shift.cash_movement(sh, "Out", 300, "x")
        m = shift.cash_movement(sh, "Out", 300, "x", manager="boss@orbit.test", pin="4321")
        self.assertEqual(m["approved_by"], "boss@orbit.test")
        z = shift.close_shift(sh, 150)
        self.assertEqual(flt(z["expected_cash"]), 150.0)    # 500 - 50 - 300
        self.assertEqual(flt(z["difference"]), 0.0)

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

    # ---- returns / exchange
    def _sale(self, sh, lines, pay, **kw):
        from orbit_pos.api import sales
        return sales.submit_sale(self._payload(sh, lines, pay, **kw))

    def _ensure_promo(self):
        if not frappe.db.exists("POS Promotion", {"promo_name": "b2g3"}):
            frappe.get_doc({"doctype": "POS Promotion", "promo_name": "b2g3", "promo_type": "bxgy", "buy_qty": 2, "get_qty": 3,
                            "enabled": 1}).insert()

    def test_14_percent_discount_refunds_the_sold_price(self):
        from orbit_pos.api import sales
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10, "manualPct": 20}], 20)
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", r["sales_invoice"], "grand_total")), 16.0)
        ret = sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]))
        self.assertEqual(ret["refund"], 8.0)

    def test_15_promo_line_is_exchange_only_and_credit_is_issued(self):
        from orbit_pos.api import sales
        self._ensure_promo()
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-B", "qty": 5, "price": 4}], 20)
        inv = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertTrue(inv.items[0].orbit_promo)
        with self.assertRaises(frappe.ValidationError):
            sales.create_return(inv.name, json.dumps([{"item_code": "ORB-B", "qty": 1}]), mode="refund")
        before = stock("ORB-B")
        ret = sales.create_return(inv.name, json.dumps([{"item_code": "ORB-B", "qty": 1}]), mode="credit")
        self.assertEqual(stock("ORB-B"), before + 1)
        self.assertEqual(ret["refund"], 1.6)             # 8.00 paid for 5 units, pro rata
        rec = frappe.get_doc("POS Exchange Receipt", ret["exchange_receipt"])
        self.assertEqual((rec.status, flt(rec.amount)), ("Open", 1.6))
        days = int(frappe.get_cached_doc("Orbit POS Settings").return_window_days or 0)
        if days:
            self.assertEqual((rec.expires_on - rec.issued_on).days, days)   # printed window = the setting
        # drawer cash is untouched by an exchange credit
        from orbit_pos.api import shift
        self.assertEqual(flt(shift.expected_cash(sh)), 100.0 + 8.0)

    def test_16_exchange_receipt_redeem_split_reuse_and_expiry(self):
        from orbit_pos.api import sales, exchange
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20)
        ret = sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="credit")
        rid = ret["exchange_receipt"]
        self.assertEqual(exchange.exchange_receipt_info(rid)["amount"], 10.0)
        # cheaper replacement: 4 of the 10 is used, the remaining 6 becomes a new receipt
        s2 = self._sale(sh, [{"itemId": "ORB-B", "qty": 1, "price": 4}], 0, exchange_receipt=rid)
        self.assertEqual(s2["exchange_credit_used"], 4.0)
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", s2["sales_invoice"], "grand_total")), 4.0)
        self.assertEqual(frappe.db.get_value("POS Exchange Receipt", rid, "status"), "Redeemed")
        left = frappe.get_doc("POS Exchange Receipt", s2["new_exchange_receipt"])
        self.assertEqual((left.status, flt(left.amount)), ("Open", 6.0))
        with self.assertRaises(frappe.ValidationError):               # a receipt works once
            self._sale(sh, [{"itemId": "ORB-B", "qty": 1, "price": 4}], 0, exchange_receipt=rid)
        # expired receipts are refused
        frappe.db.set_value("POS Exchange Receipt", left.name, "expires_on", frappe.utils.add_days(nowdate(), -1))
        with self.assertRaises(frappe.ValidationError):
            self._sale(sh, [{"itemId": "ORB-B", "qty": 1, "price": 4}], 0, exchange_receipt=left.name)
        # dearer replacement: credit 10 + 5 cash for a 15 item
        ret2 = sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="credit")
        s3 = self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}, {"itemId": "ORB-B", "qty": 1, "price": 4}], 4,
                        exchange_receipt=ret2["exchange_receipt"])
        self.assertEqual(flt(s3["exchange_credit_used"]), 10.0)
        self.assertFalse(s3["new_exchange_receipt"])

    def test_17_window_needs_manager_after_expiry(self):
        from orbit_pos.api import sales
        frappe.set_user("Administrator"); sh = self._shift()
        frappe.db.set_value("POS Shift", sh, {"shared_shift": 1})
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20)
        win = int(frappe.get_cached_doc("Orbit POS Settings").return_window_days or 14) or 14
        frappe.db.set_value("Sales Invoice", r["sales_invoice"], "posting_date", frappe.utils.add_days(nowdate(), -(win + 5)))
        frappe.set_user("cashier@orbit.test")
        with self.assertRaises(frappe.PermissionError):
            sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="credit")
        ok = sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="credit",
                                 manager="boss@orbit.test", pin="4321")
        self.assertEqual(ok["approved_by"], "boss@orbit.test")

    def test_18_serial_item_partial_return_selects_serials(self):
        from orbit_pos.api import sales, exchange
        if not frappe.db.exists("Item", "ORB-SN"):
            frappe.get_doc({"doctype": "Item", "item_code": "ORB-SN", "item_name": "ORB-SN", "item_group": leaf("Item Group"),
                            "stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 1, "valuation_rate": 50}).insert()
            frappe.get_doc({"doctype": "Item Price", "item_code": "ORB-SN", "price_list": "Standard Selling",
                            "price_list_rate": 100, "selling": 1}).insert()
            se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": CO,
                                 "items": [{"item_code": "ORB-SN", "qty": 4, "t_warehouse": WH, "basic_rate": 50,
                                            "use_serial_batch_fields": 1, "serial_no": "SN-1\nSN-2\nSN-3\nSN-4"}]})
            se.insert(); se.submit()
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-SN", "qty": 3, "price": 100, "serial_no": ["SN-1", "SN-2", "SN-3"]}], 300)
        inv = r["sales_invoice"]
        info = exchange.invoice_for_return(inv)
        self.assertEqual(sorted(info["lines"][0]["serials"]), ["SN-1", "SN-2", "SN-3"])
        with self.assertRaises(frappe.ValidationError):      # serials are mandatory for serial items
            sales.create_return(inv, json.dumps([{"item_code": "ORB-SN", "qty": 1}]))
        with self.assertRaises(frappe.ValidationError):      # SN-4 was never sold on this invoice
            sales.create_return(inv, json.dumps([{"item_code": "ORB-SN", "qty": 1, "serial_no": ["SN-4"]}]))
        ret = sales.create_return(inv, json.dumps([{"item_code": "ORB-SN", "qty": 2, "serial_no": ["SN-1", "SN-3"]}]))
        self.assertEqual(ret["refund"], 200.0)
        info = exchange.invoice_for_return(inv)
        self.assertEqual(info["lines"][0]["serials"], ["SN-2"])
        self.assertEqual(info["lines"][0]["left"], 1.0)
        with self.assertRaises(frappe.ValidationError):      # the same serial cannot come back twice
            sales.create_return(inv, json.dumps([{"item_code": "ORB-SN", "qty": 1, "serial_no": ["SN-1"]}]))
        sales.create_return(inv, json.dumps([{"item_code": "ORB-SN", "qty": 1, "serial_no": ["SN-2"]}]))

    def test_19_customer_receipt_active_promos_and_search(self):
        from orbit_pos.api import sales, exchange
        self._ensure_promo()
        c = exchange.create_customer("Test Customer Ahmed", "01000000001")
        self.assertTrue(exchange.search_customers("Ahmed"))
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, customer=c["name"])
        rc = exchange.get_receipt(r["sales_invoice"])
        self.assertEqual(rc["customer"], "Test Customer Ahmed")
        self.assertEqual(rc["window_days"], int(frappe.get_cached_doc("Orbit POS Settings").return_window_days or 0))
        r2 = self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10)
        self.assertEqual(exchange.get_receipt(r2["sales_invoice"])["customer"], "عميل نقدي")
        self.assertIn("b2g3", [p["name"] for p in exchange.active_promotions()])
        self.assertTrue(exchange.search_invoices(r["sales_invoice"]))
        self.assertTrue(exchange.search_invoices("Ahmed"))
