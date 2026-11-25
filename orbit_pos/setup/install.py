import frappe

CUSTOM_FIELDS = {
    "Item": [
        dict(fieldname="orbit_weighed", label="Weighed item (scale)", fieldtype="Check", insert_after="stock_uom"),
        dict(fieldname="orbit_plu", label="Scale PLU", fieldtype="Data", insert_after="orbit_weighed",
             depends_on="orbit_weighed"),
    ],
    "Sales Invoice": [
        dict(fieldname="orbit_txn_id", label="Orbit transaction id", fieldtype="Data", unique=1, read_only=1,
             no_copy=1, insert_after="naming_series"),
        dict(fieldname="orbit_shift", label="Orbit shift", fieldtype="Link", options="POS Shift", read_only=1,
             no_copy=1, insert_after="orbit_txn_id"),
        dict(fieldname="orbit_branch", label="Orbit branch", fieldtype="Data", read_only=1, no_copy=1,
             insert_after="orbit_shift"),
    ],
    "Sales Invoice Item": [
        dict(fieldname="orbit_promo", label="Sold under a promotion (exchange only)", fieldtype="Check", read_only=1,
             no_copy=1, insert_after="item_code"),
    ],
    "POS Profile": [
        dict(fieldname="orbit_sale_receipt_format", label="Sale Receipt Format", fieldtype="Select",
             options="Standard 80mm\nCompact 80mm", default="Standard 80mm", insert_after="company"),
        dict(fieldname="orbit_return_receipt_format", label="Return / Exchange Receipt Format", fieldtype="Select",
             options="Standard 80mm\nDetailed 80mm", default="Standard 80mm", insert_after="orbit_sale_receipt_format"),
    ],
    "User": [
        dict(fieldname="orbit_pos_pin", label="POS PIN", fieldtype="Password", insert_after="mobile_no"),
    ],
}


def after_install():
    for role in ("POS Manager", "POS User"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    for dt, fields in CUSTOM_FIELDS.items():
        for f in fields:
            name = f"{dt}-{f['fieldname']}"
            if not frappe.db.exists("Custom Field", name):
                frappe.get_doc({"doctype": "Custom Field", "dt": dt, "module": "Orbit POS", **f}).insert(ignore_permissions=True)
    frappe.db.commit()
