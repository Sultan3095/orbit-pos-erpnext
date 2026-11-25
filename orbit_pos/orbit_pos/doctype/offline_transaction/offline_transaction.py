import frappe
from frappe.model.document import Document


class OfflineTransaction(Document):
    def validate(self):
        if self.is_new() and frappe.db.exists("Offline Transaction", {"txn_id": self.txn_id}):
            frappe.throw(frappe._("Duplicate transaction"), frappe.DuplicateEntryError)

