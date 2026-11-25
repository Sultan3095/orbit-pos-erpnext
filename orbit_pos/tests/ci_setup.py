"""CI helper: finishes the ERPNext setup wizard so the test site has a company, chart of accounts and defaults."""
import frappe
from frappe.utils import getdate, nowdate


def run():
    if frappe.db.get_single_value("System Settings", "setup_complete") and frappe.db.exists("Company", "Orbit Test"):
        return
    y = getdate(nowdate()).year
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
    setup_complete({
        "language": "English", "country": "Egypt", "timezone": "Africa/Cairo", "currency": "EGP",
        "full_name": "Test Admin", "email": "admin@example.com", "password": "admin",
        "company_name": "Orbit Test", "company_abbr": "OT", "domains": ["Retail"],
        "chart_of_accounts": "Standard", "fy_start_date": f"{y}-01-01", "fy_end_date": f"{y}-12-31",
        "company_tagline": "x", "bank_account": "Bank",
    })
    frappe.db.commit()
    print("setup complete; companies:", frappe.get_all("Company", pluck="name"))
