"""Supplier-invoice Excel import. All rows are validated first; one bad row blocks the whole file."""
import re
import frappe
from frappe.utils import flt, getdate, cint
from .common import require_pos_user

COLS = {
    "barcode": ["barcode", "code", "الباركود", "الكود", "باركود", "كود"],
    "name": ["name", "item", "الاسم", "الصنف", "اسم الصنف"],
    "qty": ["qty", "quantity", "الكمية", "كمية"],
    "cost": ["cost", "التكلفة", "سعر الشراء", "تكلفة"],
    "discount": ["discount", "discount%", "الخصم", "الخصم %"],
    "batch": ["batch", "الباتش", "رقم التشغيلة"],
    "expiry": ["expiry", "expiry date", "تاريخ الصلاحية", "الصلاحية"],
    "serial": ["serial", "serials", "السيريال", "سيريال"],
    "price": ["price", "selling price", "سعر البيع"],
}
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).translate(AR_DIGITS).replace(",", "").strip())


def _map_headers(row):
    idx = {}
    for i, h in enumerate(row):
        key = re.sub(r"\s+", " ", str(h or "").strip().lower())
        for k, names in COLS.items():
            if key in [n.lower() for n in names]:
                idx.setdefault(k, i)
    return idx


def parse_rows(rows):
    """Pure function over a list of lists. Returns (parsed_rows, errors)."""
    if not rows:
        return [], [(0, "empty file")]
    idx = _map_headers(rows[0])
    errors = []
    for need in ("barcode", "qty", "cost"):
        if need not in idx:
            errors.append((1, f"missing column: {need}"))
    if errors:
        return [], errors
    out, seen_serials = [], set()
    for n, r in enumerate(rows[1:], start=2):
        if not any(c not in (None, "") for c in r):
            continue
        g = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else None
        try:
            qty, cost = num(g("qty")), num(g("cost"))
            if qty is None or qty <= 0:
                errors.append((n, "quantity must be > 0")); continue
            if cost is None or cost < 0:
                errors.append((n, "cost is required")); continue
            disc = num(g("discount")) or 0
            if not 0 <= disc <= 100:
                errors.append((n, "discount must be 0-100")); continue
            exp = g("expiry")
            if exp not in (None, ""):
                exp = str(getdate(exp))
            serials = [x.strip() for x in re.split(r"[,\n;]", str(g("serial") or "")) if x.strip()]
            if serials:
                if len(serials) != int(qty):
                    errors.append((n, "serial count must equal quantity")); continue
                dup = [x for x in serials if x in seen_serials]
                if dup or len(set(serials)) != len(serials):
                    errors.append((n, "duplicate serial")); continue
                seen_serials.update(serials)
            out.append({"row": n, "barcode": str(g("barcode") or "").strip(), "name": g("name"), "qty": qty,
                        "cost": cost, "discount": disc, "batch": g("batch"), "expiry": exp or None,
                        "serials": serials, "price": num(g("price"))})
        except Exception as e:  # bad date / number
            errors.append((n, f"unreadable value ({e.__class__.__name__})"))
    return out, errors


@frappe.whitelist()
def import_supplier_invoice(file_url, supplier, bill_no, bill_date, warehouse, company, dry_run=1):
    require_pos_user()
    import openpyxl
    from frappe.utils.file_manager import get_file_path
    wb = openpyxl.load_workbook(get_file_path(file_url), data_only=True)
    rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    parsed, errors = parse_rows(rows)
    if frappe.db.exists("Purchase Invoice", {"supplier": supplier, "bill_no": bill_no, "docstatus": ["<", 2]}):
        errors.append((0, "this supplier invoice number was already imported"))
    preview = []
    for p in parsed:
        item = frappe.db.get_value("Item Barcode", {"barcode": p["barcode"]}, "parent") or \
            (p["barcode"] if frappe.db.exists("Item", p["barcode"]) else None)
        preview.append({**p, "item_code": item, "is_new": item is None})
    if errors or cint(dry_run):
        return {"ok": not errors, "errors": errors, "preview": preview}
    pi = frappe.new_doc("Purchase Invoice")
    pi.update({"supplier": supplier, "bill_no": bill_no, "bill_date": bill_date, "company": company,
               "update_stock": 1, "set_warehouse": warehouse})
    for p in preview:
        code = p["item_code"]
        if not code:
            it = frappe.get_doc({"doctype": "Item", "item_code": p["barcode"], "item_name": p["name"] or p["barcode"],
                                 "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 1,
                                 "has_serial_no": 1 if p["serials"] else 0, "has_batch_no": 1 if p["batch"] else 0,
                                 "create_new_batch": 1 if p["batch"] else 0,
                                 "barcodes": [{"barcode": p["barcode"]}]}).insert()
            code = it.name
        row = {"item_code": code, "qty": p["qty"], "rate": p["cost"], "warehouse": warehouse,
               "discount_percentage": p["discount"]}
        if p["serials"]:
            row["serial_no"] = "\n".join(p["serials"])
        if p["batch"]:
            row["use_serial_batch_fields"] = 1
            row["batch_no"] = p["batch"]
        pi.append("items", row)
    pi.insert()
    pi.submit()
    return {"ok": True, "purchase_invoice": pi.name, "errors": [], "preview": preview}
