# Orbit POS for ERPNext (work in progress, not yet installed on a real ERPNext)

Status: code written and unit-tested in isolation. It has NOT been installed on a live ERPNext site,
because no MariaDB/Redis/bench was available where it was built. Treat it as a first draft that needs
an install-and-fix pass on a real bench (v15 first).

## What is here
- `orbit_pos/logic/`: pure Python rules (promotions incl. "buy 2 get 3", EAN-13 and scale barcodes,
  returns window + pro-rata refund + cross-branch toggle, loyalty, offline idempotency). 21 unit tests pass.
- `orbit_pos/orbit_pos/doctype/`: POS Shift (one open shift per user, optional shared shift), POS Cash Movement,
  POS Promotion (+ day table), Offline Transaction (unique txn id), POS Manager Approval, Loyalty Ledger Entry,
  Orbit POS Settings (return window, cross-branch returns toggle, cashier discount limit, themes, languages).
- `orbit_pos/api/`: shift (open/close/cash in-out/Z report), sales (lookup, quote, submit_sale, create_return, next_barcode),
  purchase_import (Excel supplier invoice, all-or-nothing), reports (slow moving).
- `frontend/`: React UI (Arabic RTL / English, light/dark/blue, split cash+card, 3*barcode, offline queue,
  customer screen at `#display`). Build output goes to `orbit_pos/public/pos`.

## Install on a bench (untested)
    bench get-app /path/to/orbit_pos
    bench --site yoursite install-app orbit_pos
    bench --site yoursite migrate
    cd apps/orbit_pos/frontend && npm install && npm run build && cd - && bench build --app orbit_pos
Then: Role "POS User"/"POS Manager" to users, set each manager's POS PIN (User form), create an ERPNext POS Profile
(with Cash and Credit Card modes of payment), open `/app/orbit-pos` (v15) or `/desk/orbit-pos` (v16 moved the desk from /app to /desk).

## Not done
- Egyptian e-receipts (ETA): not implemented. Needs the current ETA e-receipt spec, a preprod account and credentials
  (credentials only via a secure vault, never chat).
- Scale: weight barcodes (PLU + weight) are parsed; direct USB/serial scale is not implemented.
- Multi-branch/multi-device sync beyond what ERPNext's own central database gives (all terminals talk to one server).
- Excel import UI screen (the API exists; the UI to upload and preview is not built yet).
- Promotion/returns/manager-approval screens in the React UI: use the Frappe desk forms for now.
- Printing/receipt template (Arabic/English) not built yet.

## Run the tests
    python3 -m unittest discover -s tests -t .          # logic + import parser
    cd frontend && npm test && npm run build && node test/e2e.mjs   # UI against a mock API

## ERPNext 15 and 16
Checked against Frappe's published v16 migration notes (https://github.com/frappe/frappe/wiki/Migrating-to-version-16 and
https://github.com/frappe/erpnext/wiki/Migration-Guide-To-ERPNext-Version-16). Applied: DocTypes sort by `creation`
(v16 default), no `frappe.db.commit()` in document hooks, API calls from the UI use POST, batch/serial rows set
`use_serial_batch_fields`, page JS is a plain function (v16 loads pages as IIFEs), no use of `get_doc(..., field=value)`.
Runtime differences: v15 = Python 3.10-3.12 + Node 18-20, v16 = Python 3.14 + Node 24.
None of this has been run on a real v15 or v16 site yet. The GitHub Actions workflow `.github/workflows/erpnext-ci.yml`
installs ERPNext v15 and v16 on GitHub's servers and runs `tests/test_integration.py` against each, so the first push
shows which version fails and why.

## License

GPL-3.0-or-later (see LICENSE). Orbit POS is open source. The web app matches the GPL used by Frappe/ERPNext. The business model is support, hosting and customization, not license sales.
