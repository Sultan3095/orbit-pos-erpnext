"""Drives a live ERPNext desk with Orbit POS: screenshots of every screen and a captioned walkthrough video."""
import sys, os, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = sys.argv[1]; os.makedirs(OUT + "/shots", exist_ok=True)
n = [0]
log = []

def cap(page, text):
    page.evaluate("""(t) => { let d = document.getElementById('orbit-cap');
      if (!d) { d = document.createElement('div'); d.id = 'orbit-cap';
        d.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;background:rgba(15,23,42,.88);color:#fff;font:600 20px Arial;padding:14px 24px;text-align:center;direction:rtl';
        document.body.appendChild(d); } d.textContent = t; }""", text)

def shot(page, name, text=None, wait=1200):
    time.sleep(wait / 1000)
    if text: cap(page, text)
    n[0] += 1
    f = f"{OUT}/shots/{n[0]:02d}-{name}.png"
    try:
        page.screenshot(path=f); log.append((name, "ok"))
    except Exception as e:
        log.append((name, "FAIL " + str(e)[:80]))
    time.sleep(1.8)

def go(page, path):
    page.goto(BASE + path, wait_until="networkidle", timeout=60000)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1366, "height": 820}, record_video_dir=OUT + "/video", record_video_size={"width": 1366, "height": 820})
    page = ctx.new_page(); page.set_default_timeout(20000)
    go(page, "/login")
    shot(page, "login", "Orbit POS على ERPNext: تسجيل الدخول")
    page.fill("#login_email", "Administrator"); page.fill("#login_password", "admin"); page.click(".btn-login")
    page.wait_for_url("**/app**", timeout=60000)
    shot(page, "desk-home", "الصفحة الرئيسية لـ ERPNext", 3000)

    # ---- the POS screen
    go(page, "/app/orbit-pos")
    time.sleep(3)
    fr = page.frame_locator("iframe")
    cap(page, "شاشة الكاشير: لازم تفتح شيفت الأول")
    shot(page, "pos-no-shift")
    try:
        fr.locator("input").first.fill("100")
        cap(page, "فتح الشيفت برصيد افتتاحي 100")
        shot(page, "pos-open-shift", None, 500)
        fr.get_by_test_id("open").click(); time.sleep(3)
        log.append(("after-open-text", fr.locator("body").inner_text()[:400]))
        cap(page, "الباركود أو الكود، وممكن تكتب 5*6221 لخمس وحدات")
        shot(page, "pos-ready")
        for code in ["5*6221", "6222", "6223"]:
            fr.get_by_test_id("scan").fill(code); fr.get_by_test_id("scan").press("Enter"); time.sleep(1.5)
        cap(page, "عرض اشتري 2 خد 3 اتحسب من السيرفر: 5 شيبسي بتتحاسب 2 بس")
        shot(page, "pos-cart-promo", None, 1500)
        fr.get_by_test_id("cash").fill("30"); fr.get_by_test_id("card").fill("0"); time.sleep(1)
        cap(page, "الدفع نقدي وبيحسب الباقي")
        shot(page, "pos-payment")
        fr.get_by_test_id("pay").click(); time.sleep(4)
        cap(page, "تمت العملية وأصبحت فاتورة مبيعات في ERPNext")
        shot(page, "pos-after-pay")
        fr.get_by_test_id("lang").select_option("en"); time.sleep(1)
        cap(page, "English / Arabic switch")
        shot(page, "pos-english")
        fr.get_by_test_id("theme").select_option("dark"); time.sleep(1)
        cap(page, "Dark theme")
        shot(page, "pos-dark")
        fr.get_by_test_id("theme").select_option("light"); fr.get_by_test_id("lang").select_option("ar")
        fr.get_by_test_id("counted").fill("125")
        cap(page, "إغلاق الشيفت بالعد الفعلي للكاش")
        fr.get_by_test_id("close").click(); time.sleep(2)
        cap(page, "تقرير الإغلاق: المتوقع والفعلي والفرق")
        shot(page, "pos-z-report")
    except Exception as e:
        log.append(("pos-flow", "FAIL " + str(e)[:200]))
        shot(page, "pos-flow-failure")

    # ---- desk screens
    screens = [
        ("/app/orbit-pos-settings", "settings", "إعدادات Orbit POS: مدة المرتجع، حد خصم الكاشير، الولاء"),
        ("/app/pos-promotion", "promotions-list", "العروض"),
        ("/app/pos-shift", "shifts-list", "الشيفتات"),
        ("/app/pos-cash-movement", "cash-movements", "حركات الكاش (داخل / خارج)"),
        ("/app/pos-manager-approval", "approvals", "سجل موافقات المدير"),
        ("/app/loyalty-ledger-entry", "loyalty", "سجل نقاط الولاء"),
        ("/app/offline-transaction", "offline-txn", "العمليات (منع تكرار البيع عند إعادة الإرسال)"),
        ("/app/sales-invoice?is_return=0", "invoices", "فواتير المبيعات الناتجة من الكاشير"),
        ("/app/sales-invoice?is_return=1", "returns", "المرتجعات"),
        ("/app/item/Chips", "item-form", "الصنف: حقول الميزان (PLU) والباركود"),
        ("/app/query-report/Stock Balance", "stock-balance", "رصيد المخزون بعد البيع والمرتجع"),
        ("/app/role", "roles", "أدوار POS User و POS Manager"),
    ]
    for path, name, text in screens:
        try:
            go(page, path); shot(page, name, text, 1500)
        except Exception as e:
            log.append((name, "FAIL " + str(e)[:80]))
    # first promotion and first shift forms
    for dt, name, text in (("pos-promotion", "promotion-form", "عرض: اشتري 2 خد 3"), ("pos-shift", "shift-form", "شيفت مقفول بالفرق")):
        try:
            go(page, f"/app/{dt}"); page.locator(".list-row-container a, .list-row a").first.click(); page.wait_for_load_state("networkidle")
            shot(page, name, text, 1500)
        except Exception as e:
            log.append((name, "FAIL " + str(e)[:80]))
    try:
        go(page, "/app/sales-invoice"); page.locator(".list-row a").first.click(); page.wait_for_load_state("networkidle")
        shot(page, "invoice-form", "فاتورة كاشير: مرتبطة بالشيفت والـ transaction id", 1500)
    except Exception as e:
        log.append(("invoice-form", "FAIL " + str(e)[:80]))
    ctx.close(); b.close()
json.dump(log, open(OUT + "/capture-log.json", "w"), indent=1)
print(json.dumps(log, indent=1))
