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
        dict(fieldname="orbit_revision_of", label="Revision of", fieldtype="Link", options="Sales Invoice", read_only=1,
             no_copy=1, insert_after="orbit_branch"),
        dict(fieldname="orbit_rev", label="Revision no.", fieldtype="Int", read_only=1, no_copy=1, insert_after="orbit_revision_of"),
        dict(fieldname="orbit_edit_reason", label="Edit reason", fieldtype="Small Text", read_only=1, no_copy=1,
             insert_after="orbit_rev"),
    ],
    "Sales Invoice Payment": [
        dict(fieldname="orbit_ref", label="Card slip / approval code", fieldtype="Data", insert_after="mode_of_payment"),
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
    hide_item_cost()
    frappe.db.commit()


COST_FIELDS = ("valuation_rate", "last_purchase_rate", "standard_rate")
COST_ROLES = ("System Manager", "Stock Manager", "Item Manager", "Purchase Manager", "Accounts Manager")


def hide_item_cost():
    """Item cost fields move to permission level 1. Only roles that deal with cost read it there; POS Manager and POS User
    do not, so a POS manager never sees an item's cost in the desk either. (Do not give POS users Accounts or Stock
    manager roles.)"""
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    from frappe.permissions import add_permission, update_permission_property
    meta = frappe.get_meta("Item")
    for f in COST_FIELDS:
        if meta.has_field(f) and meta.get_field(f).permlevel != 1:
            make_property_setter("Item", f, "permlevel", 1, "Int", validate_fields_for_doctype=False)
    for role in COST_ROLES:
        if frappe.db.exists("Role", role) and not frappe.db.exists("Custom DocPerm", {"parent": "Item", "role": role, "permlevel": 1}):
            add_permission("Item", role, 1)
            update_permission_property("Item", role, 1, "read", 1)
            update_permission_property("Item", role, 1, "write", 1)
    frappe.clear_cache(doctype="Item")
