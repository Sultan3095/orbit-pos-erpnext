import frappe
from frappe.model.document import Document


class POSShift(Document):
    def validate(self):
        # one open shift per user (also enforced per terminal when set)
        if self.status == "Open":
            clash = frappe.db.exists("POS Shift", {"user": self.user, "status": "Open", "name": ["!=", self.name]})
            if clash:
                frappe.throw(frappe._("User {0} already has an open shift ({1})").format(self.user, clash))
        if self.status == "Closed" and self.counted_cash is not None:
            self.difference = round((self.counted_cash or 0) - (self.expected_cash or 0), 2)

