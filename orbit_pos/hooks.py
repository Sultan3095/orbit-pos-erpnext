app_name = "orbit_pos"
app_title = "Orbit POS"
app_publisher = "Orbit"
app_description = "Retail POS for ERPNext: shifts, promotions, returns, offline sync, Arabic RTL"
app_email = "dev@example.com"
app_license = "MIT"
required_apps = ["erpnext"]

after_install = "orbit_pos.setup.install.after_install"

# The React UI is served as a Frappe page at /app/orbit-pos (built into public/)
app_include_js = []

doc_events = {
    "Sales Invoice": {"validate": "orbit_pos.api.sales.guard_invoice"},
}
