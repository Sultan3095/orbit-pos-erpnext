import frappe
from frappe.model.document import Document


class POSPromotion(Document):
    def validate(self):
        if self.promo_type == "bxgy" and (not self.buy_qty or not self.get_qty):
            frappe.throw(frappe._("Buy and Get quantities are required"))
        if self.promo_type == "bundle" and (not self.bundle_qty or not self.bundle_price):
            frappe.throw(frappe._("Bundle quantity and price are required"))
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(frappe._("End date is before start date"))

    def to_engine(self):
        """Dict understood by orbit_pos.logic.promotions"""
        scope = {"type": "all"}
        if self.scope_type == "Item":
            scope = {"type": "item", "value": self.scope_item}
        elif self.scope_type == "Item Group":
            scope = {"type": "group", "value": self.scope_item_group}
        days = [int(d.day_number) for d in (self.days or [])]
        return {"id": self.name, "name": self.promo_name, "active": bool(self.enabled), "type": self.promo_type,
                "scope": scope, "start": str(self.start_date or ""), "end": str(self.end_date or ""),
                "days": days, "stackable": bool(self.stackable), "priority": self.priority or 0,
                "params": {"percent": self.percent, "amount": self.amount, "buy": self.buy_qty, "get": self.get_qty,
                           "getPct": self.get_discount_percent if self.get_discount_percent is not None else 100,
                           "qty": self.bundle_qty, "price": self.bundle_price, "minTotal": self.min_total}}

