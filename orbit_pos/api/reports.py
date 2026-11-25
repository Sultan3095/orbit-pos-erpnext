import frappe
from frappe.utils import nowdate, add_days, flt
from .common import require_pos_user


@frappe.whitelist()
def slow_moving(days=30, warehouse=None, limit=200):
    """Items with stock but no (or few) sales in the last N days."""
    require_pos_user()
    since = add_days(nowdate(), -int(days))
    cond = "and b.warehouse = %(wh)s" if warehouse else ""
    rows = frappe.db.sql(f"""
        select b.item_code, i.item_name, sum(b.actual_qty) as stock,
               coalesce((select sum(sii.qty) from `tabSales Invoice Item` sii
                  join `tabSales Invoice` si on si.name=sii.parent
                  where sii.item_code=b.item_code and si.docstatus=1 and si.is_return=0
                  and si.posting_date >= %(since)s), 0) as sold,
               (select max(si.posting_date) from `tabSales Invoice Item` sii
                  join `tabSales Invoice` si on si.name=sii.parent
                  where sii.item_code=b.item_code and si.docstatus=1) as last_sale
        from `tabBin` b join `tabItem` i on i.name=b.item_code
        where b.actual_qty > 0 {cond}
        group by b.item_code, i.item_name
        having sold = 0
        order by stock desc limit %(limit)s""", {"since": since, "wh": warehouse, "limit": int(limit)}, as_dict=True)
    return rows
