import frappe
from frappe.utils.password import get_decrypted_password

MANAGER_ROLE = "POS Manager"


def settings():
    return frappe.get_cached_doc("Orbit POS Settings")


def require_pos_user():
    roles = frappe.get_roles()
    if not ({"POS User", MANAGER_ROLE, "System Manager"} & set(roles)):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


def verify_manager_pin(manager_user: str, pin: str) -> str:
    """Returns the manager user id when the PIN matches a POS Manager, else throws.
    The PIN is a Password field on User, stored encrypted by Frappe."""
    if not manager_user or not pin:
        frappe.throw(frappe._("Manager approval required"), frappe.PermissionError)
    if MANAGER_ROLE not in frappe.get_roles(manager_user):
        frappe.throw(frappe._("{0} is not a POS Manager").format(manager_user), frappe.PermissionError)
    stored = get_decrypted_password("User", manager_user, "orbit_pos_pin", raise_exception=False)
    if not stored or stored != str(pin):
        frappe.throw(frappe._("Wrong manager PIN"), frappe.PermissionError)
    return manager_user


def log_approval(manager, action, reference="", detail="", shift=None):
    frappe.get_doc({"doctype": "POS Manager Approval", "approved_by": manager,
                    "requested_by": frappe.session.user, "action": action,
                    "reference": reference, "detail": detail, "shift": shift}).insert(ignore_permissions=True)
