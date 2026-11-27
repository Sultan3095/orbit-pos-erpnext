"""CI helper: demo data for screenshots and the walkthrough video (never run on a real site)."""
import json
import frappe
from frappe.utils import nowdate
from orbit_pos.tests import test_flows as tf


def run():
    frappe.set_user("Administrator")
    tf.make_item("Chips", 4, "6221", 200)
    tf.make_item("Juice", 12, "6222", 100)
    tf.make_item("Water", 5, "6223", 100)
    leaf = tf.leaf
    if not frappe.db.exists("Customer", "Orbit Walkin"):
        frappe.get_doc({"doctype": "Customer", "customer_name": "Orbit Walkin", "customer_group": leaf("Customer Group"),
                        "territory": leaf("Territory")}).insert()
    co = tf.CO
    if not frappe.db.exists("Mode of Payment", "Credit Card"):
        frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "Credit Card", "type": "Bank"}).insert()
    mop = frappe.get_doc("Mode of Payment", "Credit Card")
    if not [a for a in mop.accounts if a.company == co]:
        acc = frappe.db.get_value("Account", {"company": co, "account_type": "Bank", "is_group": 0}, "name") or \
            frappe.db.get_value("Company", co, "default_cash_account")
        mop.append("accounts", {"company": co, "default_account": acc}); mop.save()
    name = "Orbit Demo Profile"
    if not frappe.db.exists("POS Profile", name):
        frappe.get_doc({"doctype": "POS Profile", "name": name, "company": co, "customer": "Orbit Walkin",
                        "warehouse": tf.WH, "currency": "EGP", "selling_price_list": "Standard Selling",
                        "payments": [{"mode_of_payment": "Cash", "default": 1}, {"mode_of_payment": "Credit Card"}],
                        "write_off_account": frappe.db.get_value("Company", co, "write_off_account"),
                        "write_off_cost_center": frappe.db.get_value("Company", co, "cost_center"),
                        "income_account": frappe.db.get_value("Company", co, "default_income_account"),
                        "expense_account": frappe.db.get_value("Company", co, "default_expense_account")}).insert()
    for role_user, role, pin in (("cashier@orbit.test", "POS User", None), ("boss@orbit.test", "POS Manager", "4321")):
        if not frappe.db.exists("User", role_user):
            frappe.get_doc({"doctype": "User", "email": role_user, "first_name": role_user.split("@")[0], "send_welcome_email": 0,
                            "roles": [{"role": role}, {"role": "Sales User"}, {"role": "Stock User"}, {"role": "Accounts User"}]}).insert()
        if pin:
            u = frappe.get_doc("User", role_user); u.orbit_pos_pin = pin; u.save()
    if not frappe.db.exists("POS Promotion", {"promo_name": "Buy 2 get 3 Chips"}):
        frappe.get_doc({"doctype": "POS Promotion", "promo_name": "Buy 2 get 3 Chips", "promo_type": "bxgy", "buy_qty": 2,
                        "get_qty": 3, "enabled": 1}).insert()
    tf.enable_serial()
    if not frappe.db.exists("Item", "Phone"):
        frappe.get_doc({"doctype": "Item", "item_code": "Phone", "item_name": "Phone", "item_group": leaf("Item Group"),
                        "stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 1, "valuation_rate": 50,
                        "barcodes": [{"barcode": "6230"}]}).insert()
        frappe.get_doc({"doctype": "Item Price", "item_code": "Phone", "price_list": "Standard Selling",
                        "price_list_rate": 100, "selling": 1}).insert()
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": co,
                             "items": [{"item_code": "Phone", "qty": 4, "t_warehouse": tf.WH, "basic_rate": 50,
                                        "use_serial_batch_fields": 1, "serial_no": "PH-1\nPH-2\nPH-3\nPH-4"}]})
        se.insert(); se.submit()
    st = frappe.get_doc("Orbit POS Settings")
    st.return_window_days = 7          # the receipt must print THIS value
    st.receipt_terms_ar = "الاستبدال خلال المدة المحددة بشرط سلامة المنتج وإحضار الفاتورة"
    st.receipt_terms_en = "Exchange within the stated period, item in original condition, invoice required."
    st.save()
    from orbit_pos.api import sales, shift
    # an earlier closed shift with sales, a return, a cash movement and a manager approval, so lists are not empty.
    # Idempotent: the workflow seeds once for screenshots and again inside concurrency_fixtures.
    if not frappe.db.exists("Sales Invoice", {"orbit_txn_id": "DEMO-1"}):
        sh = shift.open_shift(name, 100)["name"]
        pay = lambda t, lines, amt, **kw: json.dumps({"txn_id": t, "shift": sh, "lines": lines, "payments": [{"method": "Cash", "amount": amt}], **kw})
        r1 = sales.submit_sale(pay("DEMO-1", [{"itemId": "Chips", "qty": 5, "price": 4}, {"itemId": "Juice", "qty": 2, "price": 12}], 50))
        sales.submit_sale(pay("DEMO-2", [{"itemId": "Water", "qty": 3, "price": 5}], 20))
        sales.create_return(r1["sales_invoice"], json.dumps([{"item_code": "Juice", "qty": 1}]))
        shift.cash_movement(sh, "Out", 10, "tea and cleaning supplies")
        shift.close_shift(sh, 120)
    frappe.db.commit()
    print("seed done", frappe.get_all("Sales Invoice", pluck="name"))


def pending_close():
    """CI helper: a cashier sells and closes BLIND, leaving a close that waits for manager approval."""
    import uuid
    frappe.set_user("Administrator")
    em = "cashier.demo@orbit.test"
    if not frappe.db.exists("User", em):
        frappe.get_doc({"doctype": "User", "email": em, "first_name": "Cashier Demo", "send_welcome_email": 0,
                        "roles": [{"role": "POS User"}, {"role": "Sales User"}, {"role": "Stock User"}, {"role": "Accounts User"}]}).insert()
    frappe.set_user(em)
    from orbit_pos.api import shift, sales
    sh = shift.open_shift("Orbit Demo Profile", 100)["name"]
    p = {"txn_id": "DEMO-" + uuid.uuid4().hex[:6], "shift": sh, "lines": [{"itemId": "Chips", "qty": 3, "price": 4}],
         "payments": [{"method": "Cash", "amount": 12}]}
    r = sales.submit_sale(json.dumps(p))
    z = shift.close_shift(sh, 110)
    frappe.db.commit()
    open("/tmp/orbit_pending.json", "w").write(json.dumps({"shift": sh, "invoice": r["sales_invoice"], "pending": z.get("pending")}))


def concurrency_fixtures():
    """CI helper: data for tools/concurrency_test.py (two terminals at once). Prints one FIXTURES json line."""
    frappe.set_user("Administrator")
    run()
    from orbit_pos.api import gifts, sales, shift
    sh = shift.open_shift("Orbit Demo Profile", 0)["name"]
    card = gifts.sell_gift_card(40, sh)["card_no"]
    gifts.save_coupon(json.dumps({"code": "RACE1", "kind": "percent", "value": 10, "max_uses": 1}))
    walkin = frappe.db.get_value("POS Profile", "Orbit Demo Profile", "customer")
    rec = sales._issue_receipt(walkin, 30, None, sh)
    frappe.db.commit()
    print("FIXTURES " + json.dumps({"shift": sh, "card": card, "coupon": "RACE1", "receipt": rec.name}))
