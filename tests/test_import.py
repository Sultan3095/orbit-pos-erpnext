import sys, types, unittest
# the import parser is pure; stub the frappe modules it imports at top level
fr = types.ModuleType("frappe"); fr.whitelist = lambda *a, **k: (lambda f: f)
sys.modules.setdefault("frappe", fr)
for m in ("frappe.utils", "frappe.utils.password"):
    sys.modules.setdefault(m, types.ModuleType(m))
u = sys.modules["frappe.utils"]
from datetime import date, datetime
u.flt = float; u.cint = int
u.getdate = lambda v: v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else date.fromisoformat(str(v)[:10]))
u.nowdate = lambda: "2026-11-25"; u.add_days = lambda d, n: d
sys.modules["frappe.utils.password"].get_decrypted_password = lambda *a, **k: None
from orbit_pos.api.purchase_import import parse_rows

H = ["الباركود", "الاسم", "الكمية", "التكلفة", "الخصم %", "الباتش", "تاريخ الصلاحية", "السيريال", "سعر البيع"]


class Imp(unittest.TestCase):
    def test_good_arabic_headers_and_digits(self):
        rows, err = parse_rows([H, ["111", "شيبسي", "١٢", "٣٫٥", 0, "B1", "2027-01-31", "", 5]])
        self.assertEqual(err, [])
        self.assertEqual((rows[0]["qty"], rows[0]["cost"], rows[0]["expiry"]), (12, 3.5, "2027-01-31"))

    def test_row_errors(self):
        _, err = parse_rows([H, ["1", "a", 0, 3], ["2", "b", 1, ""], ["3", "c", 1, 2, 150]])
        self.assertEqual([e[0] for e in err], [2, 3, 4])

    def test_serials(self):
        _, err = parse_rows([H, ["1", "a", 2, 3, 0, "", "", "S1,S1"]])
        self.assertTrue(err)
        r, err = parse_rows([H, ["1", "a", 2, 3, 0, "", "", "S1,S2"], ["2", "b", 1, 3, 0, "", "", "S2"]])
        self.assertTrue(err and err[0][0] == 3)  # S2 reused in a later row

    def test_bad_date_and_missing_column(self):
        _, err = parse_rows([H, ["1", "a", 1, 3, 0, "", "not-a-date"]])
        self.assertTrue(err)
        _, err = parse_rows([["الاسم", "الكمية"], ["a", 1]])
        self.assertIn((1, "missing column: barcode"), err)

if __name__ == "__main__":
    unittest.main()
