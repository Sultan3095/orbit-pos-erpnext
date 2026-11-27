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


def enable_serial():
    """v16 hides serial numbers behind a Stock Settings switch; v15 has no such field."""
    if frappe.get_meta("Stock Settings").has_field("enable_serial_and_batch_no_for_item"):
        frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)


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
        z = shift.close_shift(sh, 150)                       # cashier closes BLIND: nothing about expected is returned
        self.assertTrue(z["pending"]); self.assertNotIn("expected_cash", z)
        frappe.set_user("boss@orbit.test")
        v = shift.pending_close_view(sh)
        self.assertEqual(flt(v["expected_cash"]), 150.0)     # 500 - 50 - 300
        self.assertEqual(flt(v["difference"]), 0.0)
        zz = shift.approve_close(sh)
        self.assertEqual(flt(zz["expected_cash"]), 150.0); self.assertEqual(flt(zz["difference"]), 0.0)

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
        enable_serial()
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


    # ---- roles, blind close, reopen, edit, void, cost
    def _user(self, email, roles):
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
                            "roles": [{"role": r} for r in roles]}).insert()
        return email

    def test_20_permission_matrix_defaults_and_overrides(self):
        from orbit_pos.api import common
        self.assertEqual(common.perm("seeCost", "boss@orbit.test"), "N")        # manager sees no cost
        self.assertEqual(common.perm("reports", "boss@orbit.test"), "Y")
        self.assertEqual(common.perm("importPurchases", "boss@orbit.test"), "N")
        self.assertEqual(common.perm("discountAbove", "cashier@orbit.test"), "A")
        self.assertEqual(common.perm("seeExpected", "cashier@orbit.test"), "N")
        self.assertEqual(common.perm("seeCost", "Administrator"), "Y")
        st = frappe.get_doc("Orbit POS Settings"); old = st.get("permissions_json")
        st.permissions_json = json.dumps({"cashier": {"priceOverride": "Y"}, "manager": {"seeCost": "Y"}}); st.save()
        frappe.clear_cache()
        try:
            self.assertEqual(common.perm("priceOverride", "cashier@orbit.test"), "Y")
            self.assertEqual(common.perm("seeCost", "boss@orbit.test"), "Y")
        finally:
            st.permissions_json = old or ""; st.save(); frappe.clear_cache()

    def test_21_cashier_cannot_import_purchases_and_manager_cannot_either(self):
        from orbit_pos.api import purchase_import
        fn = lambda *_: purchase_import.import_supplier_invoice('/x.xlsx', 's', 'b', nowdate(), WH, CO)
        for u in ("cashier@orbit.test", "boss@orbit.test"):
            frappe.set_user(u)
            with self.assertRaises(frappe.PermissionError):
                fn("x")

    def test_22_two_users_have_independent_shifts(self):
        from orbit_pos.api import shift, sales
        c2 = self._user("cashier2@orbit.test", ["POS User", "Sales User", "Stock User", "Accounts User"])
        frappe.set_user("cashier@orbit.test"); s1 = self._shift(100)
        frappe.set_user(c2); s2 = self._shift(200)
        self.assertNotEqual(s1, s2)
        sales.submit_sale(self._payload(s2, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        frappe.set_user("cashier@orbit.test")
        with self.assertRaises(frappe.PermissionError):                 # cannot sell into the other user's shift
            sales.submit_sale(self._payload(s2, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        self.assertEqual(flt(shift.expected_cash(s1)), 100.0)
        self.assertEqual(flt(shift.expected_cash(s2)), 210.0)
        shift.close_shift(s1, 100)                                      # closing one does not touch the other
        self.assertEqual(frappe.db.get_value("POS Shift", s2, "status"), "Open")

    def test_23_blind_close_needs_manager_and_not_self(self):
        from orbit_pos.api import shift, sales
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20))
        r = shift.close_shift(sh, 115)
        self.assertTrue(r["pending"])
        self.assertEqual(frappe.db.get_value("POS Shift", sh, "approval_status"), "Pending")
        self.assertFalse(frappe.db.get_value("POS Shift", sh, "expected_cash"))   # hidden while pending
        z = shift.z_report(sh); self.assertIsNone(z["expected_cash"]); self.assertIsNone(z["difference"])
        with self.assertRaises(frappe.PermissionError):                 # a cashier may not look or approve
            shift.pending_close_view(sh)
        with self.assertRaises(frappe.PermissionError):
            shift.approve_close(sh)
        shift.pending_close_view(sh, manager="boss@orbit.test", pin="4321")     # PIN of a manager works from the cashier's screen
        with self.assertRaises(frappe.PermissionError):
            shift.approve_close(sh, manager="boss@orbit.test", pin="0000")
        frappe.set_user("boss@orbit.test")
        v = shift.pending_close_view(sh)
        self.assertEqual(flt(v["expected_cash"]), 120.0); self.assertEqual(flt(v["difference"]), -5.0)
        with self.assertRaises(frappe.ValidationError):                 # difference needs a note
            shift.approve_close(sh)
        z = shift.approve_close(sh, note="counted twice, 5 short")
        self.assertEqual(flt(z["expected_cash"]), 120.0); self.assertEqual(flt(z["difference"]), -5.0)
        self.assertEqual(frappe.db.get_value("POS Shift", sh, "approved_by"), "boss@orbit.test")
        with self.assertRaises(frappe.ValidationError):
            shift.approve_close(sh, note="again")

    def test_24_closed_shift_cannot_be_voided_or_edited_until_reopened(self):
        from orbit_pos.api import shift, sales
        sh = self._shift(100)
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20)); inv = r["sales_invoice"]
        shift.close_shift(sh, 120)
        with self.assertRaises(frappe.ValidationError):
            sales.void_invoice(inv, "mistake")
        with self.assertRaises(frappe.ValidationError):
            sales.edit_invoice(inv, json.dumps({"lines": [{"itemId": "ORB-A", "qty": 1, "price": 10}], "payments": [{"method": "Cash", "amount": 10}]}), "x")
        with self.assertRaises(frappe.ValidationError):                 # not even a direct cancel from the desk
            frappe.get_doc("Sales Invoice", inv).cancel()
        shift.reopen_shift(sh, "wrong quantity")
        self.assertEqual(frappe.db.get_value("POS Shift", sh, "status"), "Open")
        self.assertEqual(frappe.db.get_value("POS Shift", sh, "reopen_count"), 1)
        before = stock("ORB-A")
        e = sales.edit_invoice(inv, json.dumps({"lines": [{"itemId": "ORB-A", "qty": 3, "price": 10}], "payments": [{"method": "Cash", "amount": 30}]}), "customer took 3")
        self.assertEqual(frappe.db.get_value("Sales Invoice", inv, "docstatus"), 2)         # original cancelled, kept for audit
        new = frappe.get_doc("Sales Invoice", e["sales_invoice"])
        self.assertEqual(new.orbit_revision_of, inv); self.assertEqual(new.orbit_rev, 1); self.assertEqual(flt(new.grand_total), 30.0)
        self.assertEqual(stock("ORB-A"), before - 1)                                         # 2 back, 3 out
        self.assertEqual(flt(shift.expected_cash(sh)), 130.0)
        v = sales.void_invoice(e["sales_invoice"], "customer cancelled")
        self.assertEqual(v["status"], "voided"); self.assertEqual(stock("ORB-A"), before + 2)
        self.assertEqual(flt(shift.expected_cash(sh)), 100.0)
        z = shift.close_shift(sh, 100); self.assertEqual(flt(z["difference"]), 0.0)

    def test_25_edit_blocked_with_returns_and_cashier_needs_manager_pin(self):
        from orbit_pos.api import shift, sales
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20)); inv = r["sales_invoice"]
        pl = json.dumps({"lines": [{"itemId": "ORB-A", "qty": 1, "price": 10}], "payments": [{"method": "Cash", "amount": 10}]})
        with self.assertRaises(frappe.PermissionError):
            sales.edit_invoice(inv, pl, "x")
        with self.assertRaises(frappe.PermissionError):
            sales.edit_invoice(inv, pl, "x", manager="boss@orbit.test", pin="0000")
        sales.create_return(inv, json.dumps([{"item_code": "ORB-A", "qty": 1}]))
        with self.assertRaises(frappe.ValidationError):
            sales.edit_invoice(inv, pl, "x", manager="boss@orbit.test", pin="4321")
        with self.assertRaises(frappe.ValidationError):
            sales.void_invoice(inv, "x", manager="boss@orbit.test", pin="4321")

    def test_26_manager_cannot_read_item_cost(self):
        frappe.set_user("Administrator")
        mona = self._user("mona@orbit.test", ["POS Manager", "Sales User"])
        frappe.set_user(mona)
        doc = frappe.get_doc("Item", "ORB-A")
        if not frappe.get_meta("Item").has_field("valuation_rate"):
            self.skipTest("no valuation_rate field")
        self.assertFalse(doc.has_permlevel_access_to("valuation_rate"))
        self.assertTrue(doc.has_permlevel_access_to("item_name"))
        frappe.set_user("Administrator")
        self.assertTrue(frappe.get_doc("Item", "ORB-A").has_permlevel_access_to("valuation_rate"))

    def test_27_return_takes_back_loyalty_points(self):
        from orbit_pos.api import sales, exchange
        s = frappe.get_doc("Orbit POS Settings"); s.currency_per_point = 10; s.save()
        c = exchange.create_customer("Loyalty Return Cust", "01000000077")
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20, customer=c["name"])
        pts = lambda: frappe.db.sql("select coalesce(sum(points),0) from `tabLoyalty Ledger Entry` where customer=%s", c["name"])[0][0]
        self.assertEqual(int(pts()), 2)
        sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]))
        self.assertEqual(int(pts()), 1)

    def test_28_loyalty_never_goes_below_zero(self):
        from orbit_pos.api import sales, exchange
        s = frappe.get_doc("Orbit POS Settings"); s.currency_per_point = 10; s.save()
        c = exchange.create_customer("Loyalty Clamp Cust", "01000000078")
        sh = self._shift()
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 20, customer=c["name"])
        pts = lambda: int(frappe.db.sql("select coalesce(sum(points),0) from `tabLoyalty Ledger Entry` where customer=%s", c["name"])[0][0])
        sales._ledger(c["name"], -2, None, "spent elsewhere")      # the customer already used the points
        self.assertEqual(pts(), 0)
        sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 2}]))
        self.assertEqual(pts(), 0)

    # ---- gift cards and coupons (same rules as the desktop app)
    def _coupon(self, code, **kw):
        from orbit_pos.api import gifts
        d = {"code": code, "kind": "percent", "value": 10}
        d.update(kw)
        gifts.save_coupon(json.dumps(d))

    def test_29_coupon_percent_exchange_only_and_limits(self):
        from orbit_pos.api import sales, gifts
        self._coupon("CPN10", value=10, max_uses=1)
        sh = self._shift()
        q = sales.quote(json.dumps({"lines": [{"itemId": "ORB-A", "qty": 3, "price": 10}], "coupon": "cpn10"}))
        self.assertEqual(flt(q["coupon_disc"]), 3.0); self.assertEqual(flt(q["net_before_tax"]), 27.0)
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 27, coupon="CPN10")
        si = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertEqual(flt(si.grand_total), 27.0); self.assertEqual(si.orbit_coupon, "CPN10")
        self.assertTrue(all(i.orbit_promo for i in si.items))
        with self.assertRaises(frappe.ValidationError):      # exchange only, no cash refund
            sales.create_return(si.name, json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="refund")
        sales.create_return(si.name, json.dumps([{"item_code": "ORB-A", "qty": 1}]), mode="credit")
        with self.assertRaises(frappe.ValidationError):      # max_uses 1 reached
            self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, coupon="CPN10")

    def test_30_coupon_min_total_dates_disabled_and_amount(self):
        from orbit_pos.api import sales
        self._coupon("MIN50", kind="amount", value=5, min_total=50)
        self._coupon("OLD", value=10, end_date="2020-01-01")
        self._coupon("OFF", value=10, enabled=0)
        sh = self._shift()
        for code in ("MIN50", "OLD", "OFF", "NOPE"):
            with self.assertRaises(frappe.ValidationError):
                sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, coupon=code))
        self._coupon("FIVE", kind="amount", value=5)
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 2, "price": 10}], 15, coupon="FIVE")
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", r["sales_invoice"], "grand_total")), 15.0)

    def test_31_coupon_per_customer_limit_and_void_frees_use(self):
        from orbit_pos.api import sales, exchange
        self._coupon("ONCE", value=10, max_per_customer=1)
        c = exchange.create_customer("Coupon Cust", "01000000091")
        sh = self._shift()
        with self.assertRaises(frappe.ValidationError):      # needs a named customer
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, coupon="ONCE"))
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 9, coupon="ONCE", customer=c["name"])
        with self.assertRaises(frappe.ValidationError):
            self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 9, coupon="ONCE", customer=c["name"])
        sales.void_invoice(r["sales_invoice"], "mistake")
        self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 9, coupon="ONCE", customer=c["name"])

    def test_32_gift_card_sale_is_liability_and_counts_in_drawer(self):
        from orbit_pos.api import gifts, shift
        sh = self._shift(100)
        before = shift.expected_cash(sh)
        c = gifts.sell_gift_card(200, sh, "Cash", customer_name="Mona")
        self.assertEqual(c["balance"], 200.0); self.assertEqual(c["status"], "active")
        self.assertEqual(shift.expected_cash(sh), before + 200)
        gl = frappe.db.sql("""select coalesce(sum(credit - debit),0) from `tabGL Entry` where voucher_no=%s and account like %s and is_cancelled=0""",
                           (c["journal_entry"], "%Gift Card Liability%"))[0][0]
        self.assertEqual(flt(gl), 200.0)                    # money held for the customer, not income
        self.assertEqual(gifts.list_gift_cards()["liability"]["open"], 200.0 + sum(
            i["balance"] for i in gifts.list_gift_cards()["cards"] if i["status"] == "active" and i["card_no"] != c["card_no"]))
        with self.assertRaises(frappe.ValidationError):
            gifts.sell_gift_card(0, sh)
        with self.assertRaises(frappe.ValidationError):
            gifts.sell_gift_card(50, sh, "Exchange Credit")
        gifts.void_gift_card(c["card_no"], "sold by mistake")   # unused: allowed, and the drawer goes back
        self.assertEqual(shift.expected_cash(sh), before)
        self.assertEqual(gifts.check_gift_card(c["card_no"])["status"], "void")

    def test_33_pay_with_gift_card_partial_return_refund_void_and_edit_block(self):
        from orbit_pos.api import gifts, sales
        sh = self._shift()
        c = gifts.sell_gift_card(100, sh, "Cash")["card_no"]
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 10, gift_card=c, gift_amount=20)
        si = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertEqual(flt(si.orbit_gift_amount), 20.0)
        self.assertEqual(sorted((p.mode_of_payment, flt(p.amount)) for p in si.payments), [("Cash", 10.0), ("Gift Card", 20.0)])
        self.assertEqual(gifts.check_gift_card(c)["balance"], 80.0)
        info = sales.invoice_for_edit(si.name)
        self.assertIn("gift", info["blockers"])
        with self.assertRaises(frappe.ValidationError):
            sales.edit_invoice(si.name, json.dumps({"lines": [{"itemId": "ORB-A", "qty": 1, "price": 10}], "payments": [{"method": "Cash", "amount": 10}]}), "x")
        with self.assertRaises(frappe.ValidationError):      # used card cannot be cancelled
            gifts.void_gift_card(c)
        ret = sales.create_return(si.name, json.dumps([{"item_code": "ORB-A", "qty": 1}]))   # 10 back: 2/3 to the card, rest cash
        self.assertAlmostEqual(ret["gift_refund"], 6.67, places=2)
        self.assertAlmostEqual(gifts.check_gift_card(c)["balance"], 86.67, places=2)
        log = [x["kind"] for x in gifts.gift_card_history(c)["log"]]
        self.assertEqual(log, ["issue", "redeem", "refund"])

    def test_34_void_gift_paid_invoice_restores_card_and_full_cover(self):
        from orbit_pos.api import gifts, sales
        sh = self._shift()
        c = gifts.sell_gift_card(100, sh, "Cash")["card_no"]
        r = sales.submit_sale(json.dumps({"txn_id": "G-" + uuid.uuid4().hex[:8], "shift": sh, "payments": [],
                                          "lines": [{"itemId": "ORB-A", "qty": 2, "price": 10}], "gift_card": c}))
        self.assertEqual(flt(r["gift_used"]), 20.0); self.assertEqual(gifts.check_gift_card(c)["balance"], 80.0)
        sales.void_invoice(r["sales_invoice"], "customer changed mind")
        self.assertEqual(gifts.check_gift_card(c)["balance"], 100.0)

    def test_35_gift_card_expired_empty_unknown_and_over_balance(self):
        from orbit_pos.api import gifts, sales
        sh = self._shift()
        c = gifts.sell_gift_card(15, sh, "Cash", expires_days=30)["card_no"]
        frappe.db.set_value("POS Gift Card", c, "expires_on", "2020-01-01")
        with self.assertRaises(frappe.ValidationError):
            self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0, gift_card=c)
        gifts.extend_gift_card(c, frappe.utils.add_days(nowdate(), 5))
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 15, gift_card=c)   # card holds 15 of 30
        self.assertEqual(flt(r["gift_used"]), 15.0); self.assertEqual(flt(frappe.db.get_value("POS Gift Card", c, "balance")), 0.0)
        with self.assertRaises(frappe.ValidationError):
            self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, gift_card=c)
        with self.assertRaises(frappe.DoesNotExistError):
            gifts.check_gift_card("NOPE-0000")

    def test_36_cashier_cannot_void_gift_card_or_save_coupon(self):
        from orbit_pos.api import gifts
        frappe.set_user("Administrator"); sh = self._shift()
        frappe.db.set_value("POS Shift", sh, {"shared_shift": 1})
        frappe.set_user("cashier@orbit.test")
        c = gifts.sell_gift_card(40, sh, "Cash")["card_no"]      # cashier may sell
        with self.assertRaises(frappe.PermissionError):
            gifts.void_gift_card(c)
        with self.assertRaises(frappe.PermissionError):
            gifts.void_gift_card(c, manager="boss@orbit.test", pin="0000")
        with self.assertRaises(frappe.PermissionError):
            gifts.save_coupon(json.dumps({"code": "NOPE1", "kind": "percent", "value": 5}))
        gifts.void_gift_card(c, "mistake", manager="boss@orbit.test", pin="4321")

    def test_38_gift_cards_by_value_shift_block_and_write_off(self):
        from orbit_pos.api import gifts, shift
        sh = self._shift(100)
        a = gifts.sell_gift_card(733, sh, "Cash")["card_no"]
        gifts.sell_gift_card(733, sh, "Cash")
        gifts.sell_gift_card(744, sh, "Cash")
        blk = gifts.shift_gift_block(sh)
        self.assertEqual([(r["value"], r["count"], r["total"]) for r in blk["by_value"]], [(733.0, 2, 1466.0), (744.0, 1, 744.0)])
        self.assertEqual(blk["sold_cash"], 2210.0)
        before = shift.expected_cash(sh)
        r = self._sale(sh, [{"itemId": "ORB-A", "qty": 3, "price": 10}], 0, gift_card=a, gift_amount=30)
        self.assertEqual(flt(r["gift_used"]), 30.0)
        self.assertEqual(shift.expected_cash(sh), before)            # redeeming moves no drawer cash
        self.assertEqual(gifts.shift_gift_block(sh)["redeemed"], 30.0)
        z = shift.z_report(sh)
        self.assertEqual(z["gift_sold_cash"], 2210.0); self.assertEqual(z["gift_redeemed"], 30.0)
        row = [x for x in gifts.gift_by_value()["rows"] if x["value"] == 733.0][0]
        self.assertEqual((row["sold"], row["partly"], row["untouched"]), (2, 1, 1))
        with self.assertRaises(frappe.ValidationError):
            gifts.write_off_gift_card(a, "not expired")
        frappe.db.set_value("POS Gift Card", a, "expires_on", "2020-01-01")
        with self.assertRaises(frappe.ValidationError):
            gifts.write_off_gift_card(a, "")
        r = gifts.write_off_gift_card(a, "expired a year ago")
        self.assertEqual(r["written_off"], 703.0); self.assertEqual(r["status"], "writtenoff")
        gl = frappe.db.sql("""select coalesce(sum(debit - credit),0) from `tabGL Entry` where voucher_no=%s and account like %s and is_cancelled=0""",
                           (r["journal_entry"], "%Gift Card Liability%"))[0][0]
        self.assertEqual(flt(gl), 703.0)                              # the liability is closed
        with self.assertRaises(frappe.ValidationError):
            gifts.write_off_gift_card(a, "again")
        with self.assertRaises(frappe.ValidationError):
            self._sale(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0, gift_card=a)
        row = [x for x in gifts.gift_by_value()["rows"] if x["value"] == 733.0][0]
        self.assertEqual((row["written_off_count"], row["written_off_total"]), (1, 703.0))

    def test_40_gift_card_design_is_per_store_and_system_manager_only(self):
        from orbit_pos.api import gifts
        d0 = gifts.gift_design()
        self.assertEqual(set(d0), {"client_name", "client_logo", "color_1", "color_2", "accent", "terms_ar", "terms_en"})
        out = gifts.save_gift_design("سوبر ماركت النور", "/files/nour.png", "#0A5C36", "#1BA39C", "#F2A93B", "شرط 1\nشرط 2", "Valid at Al Nour")
        self.assertEqual(out["client_name"], "سوبر ماركت النور"); self.assertEqual(out["color_1"], "#0A5C36")
        self.assertEqual(gifts.print_gift_cards(500, 1)["design"]["client_logo"], "/files/nour.png")      # the print call returns the design the sheet uses
        frappe.set_user("cashier@orbit.test")
        try:
            with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
                gifts.save_gift_design("x")
        finally:
            frappe.set_user("Administrator")

    def test_39_printed_cards_unique_and_value_checked_on_sale(self):
        from orbit_pos.api import gifts
        sh = self._shift()
        cards = gifts.print_gift_cards(500, 6)["cards"]
        self.assertEqual(len({c["card_no"] for c in cards}), 6)
        with self.assertRaises(frappe.ValidationError):
            gifts.print_gift_cards(500, 0)
        with self.assertRaises(frappe.ValidationError):
            gifts.sell_gift_card(200, sh, "Cash", card_no=cards[0]["card_no"])      # printed as 500
        c = gifts.sell_gift_card(500, sh, "Cash", card_no=cards[0]["card_no"])
        self.assertEqual(c["card_no"], cards[0]["card_no"])
        self.assertTrue(frappe.db.get_value("POS Printed Gift Card", cards[0]["card_no"], "sold_on"))

    def test_37_theme_is_per_user_and_validated(self):
        from orbit_pos.api import shift
        frappe.set_user("cashier@orbit.test")
        shift.set_theme("galaxy")
        self.assertEqual(shift.my_permissions()["theme"], "galaxy")
        with self.assertRaises(frappe.ValidationError):
            shift.set_theme("neon")
        frappe.set_user("boss@orbit.test")
        self.assertNotEqual(shift.my_permissions()["theme"], "galaxy")     # another user keeps his own (default: brand in the UI)
        shift.set_theme("dark")
        frappe.set_user("cashier@orbit.test")
        self.assertEqual(shift.my_permissions()["theme"], "galaxy")

    # ---- review fixes (each one failed before the fix)
    def test_41_price_comes_from_the_server(self):
        from orbit_pos.api import sales
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        with self.assertRaises(frappe.PermissionError):                 # sells a 10 item for 1
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 1}], 1))
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))   # the real price is fine
        self.assertEqual(r["grand_total"], 10.0)
        frappe.set_user("Administrator")                                # System Manager may override
        sh2 = self._shift(100)
        r = sales.submit_sale(self._payload(sh2, [{"itemId": "ORB-A", "qty": 1, "price": 7}], 7))
        self.assertEqual(r["grand_total"], 7.0)

    def test_42_amount_discounts_count_against_the_cashier_limit(self):
        from orbit_pos.api import sales
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        with self.assertRaises(frappe.PermissionError):                 # 9 off a 10 item = 90%
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10, "manualAmt": 9}], 1))
        with self.assertRaises(frappe.PermissionError):                 # invoice amount discount
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 1, inv_amt=9))

    def test_43_bad_payments_are_refused(self):
        from orbit_pos.api import sales
        sh = self._shift(100)
        for pay in ([{"method": "Cash", "amount": -5}, {"method": "Cash", "amount": 15}], [{"method": "Cash", "amount": 0}],
                    [{"method": "Bitcoin", "amount": 10}]):
            with self.assertRaises(frappe.ValidationError):
                sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0, payments=pay))

    def test_44_walkin_customer_never_earns_or_redeems_points(self):
        from orbit_pos.api import sales
        sh = self._shift(100)
        st = frappe.get_doc("Orbit POS Settings"); st.currency_per_point = 1; st.value_per_point = 1; st.save()
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        self.assertEqual(frappe.db.count("Loyalty Ledger Entry", {"sales_invoice": r["sales_invoice"]}), 0)
        with self.assertRaises(frappe.ValidationError):
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10, redeem_points=5))

    def test_45_z_report_and_cash_movement_are_guarded(self):
        from orbit_pos.api import shift
        frappe.set_user("boss@orbit.test"); sh = self._shift(100)
        frappe.set_user("cashier@orbit.test")
        with self.assertRaises(frappe.PermissionError):                 # not his shift
            shift.z_report(sh)
        with self.assertRaises(frappe.PermissionError):
            shift.cash_movement(sh, "Out", 5, "taking the manager's cash")
        frappe.set_user("boss@orbit.test")
        self.assertEqual(shift.z_report(sh)["shift"], sh)

    def test_46_return_needs_an_open_shift(self):
        from orbit_pos.api import sales
        frappe.set_user("boss@orbit.test"); sh = self._shift(100)
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        frappe.db.set_value("POS Shift", sh, "status", "Closed")
        with self.assertRaises(frappe.ValidationError):
            sales.create_return(r["sales_invoice"], json.dumps([{"item_code": "ORB-A", "qty": 1}]))

    def test_47_gift_lists_are_for_managers_and_numbers_are_long(self):
        from orbit_pos.api import gifts
        frappe.set_user("cashier@orbit.test")
        for fn in (gifts.list_gift_cards, gifts.gift_by_value, gifts.list_coupons):
            with self.assertRaises(frappe.PermissionError):
                fn()
        frappe.set_user("Administrator"); sh = self._shift(100)
        no = gifts.print_gift_cards(50, 1)["cards"][0]["card_no"]
        self.assertEqual(len(no), 14)                                   # GC + 12 digits
        liab = gifts.list_gift_cards()["liability"]
        self.assertGreaterEqual(liab["open"], 0)

    def test_48_wrong_gift_numbers_are_throttled(self):
        from orbit_pos.api import gifts
        frappe.set_user("cashier@orbit.test"); frappe.cache().delete_value("orbit_gift_miss:cashier@orbit.test")
        for i in range(10):
            with self.assertRaises(frappe.DoesNotExistError):
                gifts.check_gift_card("GC0000000%d" % i)
        with self.assertRaises(frappe.PermissionError):
            gifts.check_gift_card("GC00000099")
        frappe.cache().delete_value("orbit_gift_miss:cashier@orbit.test")

    def test_49_next_barcode_needs_edit_items_and_one_open_shift(self):
        from orbit_pos.api import sales, shift
        frappe.set_user("cashier@orbit.test")
        with self.assertRaises(frappe.PermissionError):
            sales.next_barcode()
        self._shift(100)
        with self.assertRaises(frappe.ValidationError):
            shift.open_shift(self.profile, 50)
        with self.assertRaises(frappe.PermissionError):
            frappe.db.set_value("POS Shift", {"user": "cashier@orbit.test"}, "status", "Closed")
            shift.open_shift(self.profile, 50, shared=1)

    # ---- provider payments and ETA e-receipts (mock mode, built from the docs)
    def _settings(self, **kw):
        st = frappe.get_doc("Orbit POS Settings")
        for k, v in kw.items():
            st.set(k, v)
        st.save()
        return st

    def test_50_paymob_mock_flow_and_sale_consumption(self):
        from orbit_pos.api import payments, sales
        self._settings(payments_mode="mock", paymob_public_key="pk_mock", paymob_integration_ids="12345")
        st = frappe.get_doc("Orbit POS Settings"); st.paymob_secret_key = "sk_mock"; st.save()
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        txn = "T-" + uuid.uuid4().hex[:8]
        att = payments.create_payment("paymob", json.dumps({"txn_id": txn, "shift": sh, "amount": 10,
                                                            "lines": [{"itemId": "ORB-A", "name": "ORB-A", "qty": 1, "price": 10}]}))
        self.assertEqual(att["state"], "pending")
        self.assertIn("publicKey=pk_mock", att["checkout_url"])
        with self.assertRaises(frappe.ValidationError):          # not paid yet
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0,
                                            txn_id=txn, payments=[{"method": "Paymob", "amount": 10, "attempt": att["name"]}]))
        payments.mock_settle(att["name"], "paid")
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0,
                                          txn_id=txn, payments=[{"method": "Paymob", "amount": 10, "attempt": att["name"]}]))
        self.assertEqual(r["status"], "created")
        si = frappe.get_doc("Sales Invoice", r["sales_invoice"])
        self.assertEqual(si.payments[0].mode_of_payment, "Paymob")
        with self.assertRaises(frappe.DuplicateEntryError):      # one attempt, one sale
            sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 0,
                                            txn_id="T-" + uuid.uuid4().hex[:8],
                                            payments=[{"method": "Paymob", "amount": 10, "attempt": att["name"]}]))

    def test_51_provider_payments_off_are_refused_and_fawry_mock(self):
        from orbit_pos.api import payments, sales
        self._settings(payments_mode="off")
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        with self.assertRaises(frappe.ValidationError):
            payments.create_payment("fawry", json.dumps({"txn_id": "X-1", "shift": sh, "amount": 4, "lines": []}))
        self._settings(payments_mode="mock", fawry_merchant_code="MC1")
        st = frappe.get_doc("Orbit POS Settings"); st.fawry_secure_key = "sekret"; st.save()
        att = payments.create_payment("fawry", json.dumps({"txn_id": "X-2", "shift": sh, "amount": 4,
                                                           "lines": [{"itemId": "ORB-B", "name": "ORB-B", "qty": 1, "price": 4}]}))
        self.assertTrue(att["provider_ref"].startswith("FAWRY-"))
        self.assertIn("Fawry", att["instructions"])
        payments.mock_settle(att["name"], "paid")
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-B", "qty": 1, "price": 4}], 0,
                                            txn_id="X-2", payments=[{"method": "Fawry", "amount": 4, "attempt": att["name"]}]))
        self.assertEqual(r["status"], "created")

    def test_52_eta_queue_submit_accept_and_reject(self):
        from orbit_pos.api import eta, sales
        self._settings(eta_enabled=1, eta_environment="Mock", eta_seller_id="113317713", eta_seller_name="Orbit Test",
                       eta_governate="Cairo", eta_region_city="Nasr City", eta_street="10 St", eta_building="10", eta_branch_id="1")
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        name = frappe.db.get_value("POS ETA Receipt", {"sales_invoice": r["sales_invoice"]}, "name")
        self.assertTrue(name, "receipt was queued on sale")
        frappe.set_user("Administrator")
        info = eta.eta_submit(name)
        self.assertEqual(info["state"], "accepted")
        self.assertTrue(info["long_id"].startswith("MOCK"))
        with self.assertRaises(frappe.ValidationError):          # no double submission
            eta.eta_submit(name)
        rec = frappe.get_doc("POS ETA Receipt", name)
        rec.state = "rejected"; rec.error = "x"; rec.save()
        eta.eta_retry(name)
        self.assertEqual(frappe.db.get_value("POS ETA Receipt", name, "state"), "queued")

    def test_53_eta_off_queues_nothing_and_live_refuses(self):
        from orbit_pos.api import eta, sales
        self._settings(eta_enabled=0)
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        r = sales.submit_sale(self._payload(sh, [{"itemId": "ORB-A", "qty": 1, "price": 10}], 10))
        self.assertFalse(frappe.db.exists("POS ETA Receipt", {"sales_invoice": r["sales_invoice"]}))
        self._settings(eta_enabled=1, eta_environment="Preprod")
        frappe.set_user("Administrator")
        rec = frappe.get_doc({"doctype": "POS ETA Receipt", "sales_invoice": r["sales_invoice"], "state": "queued",
                              "receipt_json": json.dumps({"header": {"uuid": "0" * 64, "receiptNumber": "X",
                                                                     "dateTimeIssued": "2026-01-01T00:00:00Z"}})})
        rec.insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            eta.eta_submit(rec.name)

    def test_54_loyalty_redemption_needs_registered_phone_or_manager_pin(self):
        from orbit_pos.api import sales
        st = frappe.get_doc("Orbit POS Settings"); st.currency_per_point = 1; st.value_per_point = 1; st.save()
        if not frappe.db.exists("Customer", "Loyal Mona"):
            frappe.get_doc({"doctype": "Customer", "customer_name": "Loyal Mona", "customer_group": leaf("Customer Group"),
                            "territory": leaf("Territory"), "mobile_no": "0105551234"}).insert()
        frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
        line = [{"itemId": "ORB-A", "qty": 1, "price": 10}]
        r = sales.submit_sale(self._payload(sh, line, 10, customer="Loyal Mona"))          # earns 10 points
        self.assertEqual(r["status"], "created")
        with self.assertRaises(frappe.PermissionError):                                    # no phone, no PIN
            sales.submit_sale(self._payload(sh, line, 5, customer="Loyal Mona", redeem_points=5))
        with self.assertRaises(frappe.PermissionError):                                    # wrong phone
            sales.submit_sale(self._payload(sh, line, 5, customer="Loyal Mona", redeem_points=5, loyalty_phone="0109999999"))
        r2 = sales.submit_sale(self._payload(sh, line, 5, customer="Loyal Mona", redeem_points=5, loyalty_phone="0105551234"))
        self.assertEqual(r2["status"], "created")                                          # registered phone, no PIN needed
        r3 = sales.submit_sale(self._payload(sh, line, 5, customer="Loyal Mona", redeem_points=5,
                                           manager="boss@orbit.test", pin="4321"))         # manager override, no phone
        self.assertEqual(r3["status"], "created")
        self.assertTrue(frappe.db.exists("POS Manager Approval", {"action": "Loyalty Phone Override",
                                                                  "requested_by": "cashier@orbit.test"}))

    def test_55_recount_send_back_and_second_approval(self):
        from orbit_pos.api import shift
        if not frappe.db.exists("User", "boss2@orbit.test"):
            u = frappe.get_doc({"doctype": "User", "email": "boss2@orbit.test", "first_name": "boss2", "send_welcome_email": 0,
                                "roles": [{"role": "POS Manager"}, {"role": "Sales User"}, {"role": "Stock User"},
                                        {"role": "Accounts User"}]}).insert()
        u = frappe.get_doc("User", "boss2@orbit.test"); u.orbit_pos_pin = "9876"; u.save()
        st = frappe.get_doc("Orbit POS Settings"); st.second_approval_above = 100; st.save()
        try:
            frappe.set_user("cashier@orbit.test"); sh = self._shift(100)
            z = shift.close_shift(sh, 90)                                  # blind close, wrong count
            self.assertTrue(z["pending"])
            frappe.set_user("boss@orbit.test")
            rb = shift.send_back_for_recount(sh, note="count again")       # approver sends it back
            self.assertEqual(rb["approval_status"], "Recount")
            with self.assertRaises(frappe.ValidationError):                # cannot approve a sent-back close
                shift.approve_close(sh)
            frappe.set_user("cashier@orbit.test")
            with self.assertRaises(frappe.ValidationError):              # negative count refused
                shift.recount_shift(sh, -1)
            rc = shift.recount_shift(sh, 80, "recounted")                  # new count, back to Pending
            self.assertTrue(rc["pending"])
            frappe.set_user("boss@orbit.test")
            z2 = shift.approve_close(sh, note="accepted")                  # diff 20 < 100: one approver is enough
            self.assertEqual(z2["approval_status"], "Approved")
            self.assertFalse(frappe.db.get_value("POS Shift", sh, "second_approved_by"))
            frappe.set_user("cashier@orbit.test"); sh2 = self._shift(100)
            shift.close_shift(sh2, 250)                                    # diff +150 > threshold 100
            frappe.set_user("boss@orbit.test")
            with self.assertRaises(frappe.PermissionError):                # no second manager at all
                shift.approve_close(sh2, note="big diff")
            with self.assertRaises(frappe.PermissionError):                # second approver same as first
                shift.approve_close(sh2, note="big diff", second_manager="boss@orbit.test", second_pin="4321")
            z3 = shift.approve_close(sh2, note="big diff", second_manager="boss2@orbit.test", second_pin="9876")
            self.assertEqual(z3["approval_status"], "Approved")
            self.assertEqual(frappe.db.get_value("POS Shift", sh2, "second_approved_by"), "boss2@orbit.test")
            self.assertTrue(frappe.db.exists("POS Manager Approval", {"action": "Close Second Approval", "shift": sh2}))
        finally:
            st = frappe.get_doc("Orbit POS Settings"); st.second_approval_above = 0; st.save()
