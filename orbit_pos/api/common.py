import frappe
from frappe.utils.password import get_decrypted_password

MANAGER_ROLE = "POS Manager"


def settings():
    return frappe.get_cached_doc("Orbit POS Settings")


def require_pos_user():
    roles = frappe.get_roles()
    if not ({"POS User", MANAGER_ROLE, "System Manager"} & set(roles)):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


# Permission matrix: key -> (cashier, manager, system) as Y (allowed), A (needs an approver's PIN), N (denied).
# Same keys and defaults as the desktop app. The System Manager role always has everything.
PERMS = [["sell", "Y", "Y", "Y"], ["discountUpTo", "Y", "Y", "Y"], ["discountAbove", "A", "Y", "Y"], ["priceOverride", "N", "Y", "Y"], ["voidLine", "Y", "Y", "Y"], ["customers", "Y", "Y", "Y"], ["returnInWindow", "Y", "Y", "Y"], ["returnAfterWindow", "A", "Y", "Y"], ["exchangeReceipt", "Y", "Y", "Y"], ["reprint", "Y", "Y", "Y"], ["editInvoice", "N", "Y", "Y"], ["voidInvoice", "N", "Y", "Y"], ["shiftOwn", "Y", "Y", "Y"], ["cashMove", "Y", "Y", "Y"], ["cashOutAbove", "A", "Y", "Y"], ["seeExpected", "N", "Y", "Y"], ["viewOtherShifts", "N", "Y", "Y"], ["openDrawer", "N", "Y", "Y"], ["viewItems", "Y", "Y", "Y"], ["editItems", "N", "Y", "Y"], ["seeCost", "N", "N", "Y"], ["promos", "N", "Y", "Y"], ["importPurchases", "N", "N", "Y"], ["marginTool", "N", "N", "Y"], ["reports", "N", "Y", "Y"], ["logs", "N", "Y", "Y"], ["approve", "N", "Y", "Y"], ["settings", "N", "N", "Y"], ["users", "N", "N", "Y"], ["backup", "N", "N", "Y"]]
DEFAULTS = {k: {"cashier": a, "manager": b, "system": c} for k, a, b, c in PERMS}
LOCKED = ["settings", "users", "backup"]


def role_of(user=None):
    roles = set(frappe.get_roles(user or frappe.session.user))
    if "System Manager" in roles or (user or frappe.session.user) == "Administrator":
        return "system"
    if MANAGER_ROLE in roles:
        return "manager"
    if "POS User" in roles:
        return "cashier"
    return None


def matrix():
    """Defaults overlaid with the System Manager's edits (Orbit POS Settings > permissions_json)."""
    out = {r: {k: DEFAULTS[k][r] for k in DEFAULTS} for r in ("cashier", "manager", "system")}
    try:
        custom = frappe.parse_json(settings().get("permissions_json") or "{}") or {}
    except Exception:
        custom = {}
    for r in ("cashier", "manager"):
        for k, v in (custom.get(r) or {}).items():
            if k in DEFAULTS and v in ("Y", "A", "N"):
                out[r][k] = v
    return out


def perm(key, user=None):
    role = role_of(user)
    if role is None or key not in DEFAULTS:
        return "N"
    if role == "system":
        return "Y"
    return matrix()[role][key]


def can(key, user=None):
    return perm(key, user) == "Y"


def require(key):
    if not can(key):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


def approver_for(key, manager=None, pin=None, exclude_user=None):
    """The user who approves an action: the current user when he may do it himself, else the user whose PIN was given.
    The approver must hold `key` with Y."""
    me = frappe.session.user
    if can(key, me) and me != exclude_user:
        return me
    who = verify_manager_pin(manager, pin)
    if not can(key, who):
        frappe.throw(frappe._("{0} may not approve this").format(who), frappe.PermissionError)
    if who == exclude_user:
        frappe.throw(frappe._("You cannot approve your own action"), frappe.PermissionError)
    return who


def verify_manager_pin(manager_user: str, pin: str) -> str:
    """Returns the approver's user id when the PIN matches a user who may approve, else throws.
    The PIN is a Password field on User, stored encrypted by Frappe."""
    if not manager_user or not pin:
        frappe.throw(frappe._("Manager approval required"), frappe.PermissionError)
    if not can("approve", manager_user):
        frappe.throw(frappe._("{0} is not a POS Manager").format(manager_user), frappe.PermissionError)
    stored = get_decrypted_password("User", manager_user, "orbit_pos_pin", raise_exception=False)
    if not stored or stored != str(pin):
        frappe.throw(frappe._("Wrong manager PIN"), frappe.PermissionError)
    return manager_user


def log_approval(manager, action, reference="", detail="", shift=None):
    frappe.get_doc({"doctype": "POS Manager Approval", "approved_by": manager,
                    "requested_by": frappe.session.user, "action": action,
                    "reference": reference, "detail": detail, "shift": shift}).insert(ignore_permissions=True)
