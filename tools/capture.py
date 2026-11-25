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
    def _on_resp(r):
        if "orbit_pos.api." in r.url and r.status >= 400:
            try: body = r.text()[:300]
            except Exception: body = ""
            log.append(("api", r.status, r.url.split("orbit_pos.api.")[-1][:60], body))
    page.on("response", _on_resp)
    go(page, "/login")
    shot(page, "login", "Orbit POS على ERPNext: تسجيل الدخول")
    page.fill("#login_email", "Administrator"); page.fill("#login_password", "admin"); page.press("#login_password", "Enter")
    page.wait_for_function("() => !location.pathname.startsWith('/login')", timeout=60000)   # v15 lands on /app, v16 on /desk
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
        cap(page, "العروض الشغالة النهارده ظاهرة فوق شاشة الكاشير")
        assert fr.get_by_test_id("promo-chip").count() >= 1, "no active promo chip on the cashier screen"
        shot(page, "pos-active-promos")
        fr.get_by_test_id("cust-new").click(); fr.get_by_test_id("nc-name").fill("أحمد محمود"); fr.get_by_test_id("nc-phone").fill("01012345678")
        fr.get_by_test_id("nc-save").click(); time.sleep(2)
        assert "أحمد" in fr.get_by_test_id("customer-name").inner_text(), "customer not selected"
        cap(page, "اختيار العميل من شاشة الكاشير (الافتراضي: عميل نقدي)")
        shot(page, "pos-customer")
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
        cap(page, "فاتورة الطباعة: اسم العميل والشروط والأحكام من القالب")
        fr.get_by_test_id("receipt-modal").wait_for(); time.sleep(1)
        rtxt = fr.get_by_test_id("receipt-sheet").inner_text()
        assert "أحمد محمود" in rtxt and "Terms" not in "" and "الاستبدال" in rtxt, "sale receipt missing customer or terms: " + rtxt[:300]
        shot(page, "pos-receipt-sale", None, 800)
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        cap(page, "تمت العملية وأصبحت فاتورة مبيعات في ERPNext")
        shot(page, "pos-after-pay")
        fr.get_by_test_id("lang").select_option("en"); time.sleep(1)
        cap(page, "English / Arabic switch")
        shot(page, "pos-english")
        fr.get_by_test_id("theme").select_option("dark"); time.sleep(1)
        cap(page, "Dark theme")
        shot(page, "pos-dark")
        fr.get_by_test_id("theme").select_option("light"); fr.get_by_test_id("lang").select_option("ar")
        # ---- returns / exchange, all from the POS screen
        fr.get_by_test_id("tab-returns").click(); time.sleep(1)
        fr.get_by_test_id("ret-search").fill("أحمد"); fr.get_by_test_id("ret-find").click(); time.sleep(2)
        cap(page, "المرتجعات: البحث عن الفاتورة بالاسم أو التليفون أو السيريال"); shot(page, "ret-search")
        # re-print a CLOSED order from the list, any time
        fr.get_by_test_id("inv-reprint").first.click(); time.sleep(1.5)
        fr.get_by_test_id("receipt-modal").wait_for()
        rp = fr.get_by_test_id("receipt-sheet").inner_text()
        assert "ACC-SINV" in rp and fr.get_by_test_id("print-btn").count() == 1, "reprint of a closed invoice failed: " + rp[:200]
        cap(page, "إعادة طباعة فاتورة مقفولة في أي وقت"); shot(page, "ret-reprint")
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        fr.get_by_test_id("inv-row").first.click(); time.sleep(2)
        cap(page, "بنود الفاتورة والمتبقي للإرجاع. بند العرض: استبدال فقط")
        shot(page, "ret-invoice")
        fr.get_by_test_id("ret-qty-0").fill("1"); time.sleep(1)
        assert fr.get_by_test_id("mode-refund").is_disabled(), "refund must be disabled for a promo line"
        cap(page, "الاسترداد النقدي متقفل لأن البند عليه عرض"); shot(page, "ret-promo-exchange-only")
        fr.get_by_test_id("ret-confirm").click(); fr.get_by_test_id("receipt-modal").wait_for(); time.sleep(1.5)
        rt = fr.get_by_test_id("receipt-sheet").inner_text()
        assert "7" in fr.get_by_test_id("r-window").inner_text(), "window on receipt is not the configured 7: " + rt
        assert "EXR-" in rt and "1.60" in rt, "exchange receipt missing: " + rt
        cap(page, "إشعار الاستبدال مطبوع: القيمة والصلاحية من الإعدادات (7 أيام) والباركود")
        shot(page, "ret-exchange-receipt", None, 800)
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        xr_no = fr.get_by_test_id("ret-receipt-no").inner_text()
        shot(page, "ret-done", "تم إصدار إشعار الاستبدال " + xr_no)
        fr.get_by_test_id("ret-use-now").click(); time.sleep(1.5)
        assert fr.get_by_test_id("xr-applied").count() == 1, "exchange credit not applied"
        fr.get_by_test_id("scan").fill("6222"); fr.get_by_test_id("scan").press("Enter"); time.sleep(1.5)
        fr.get_by_test_id("cash").fill("11"); time.sleep(1)
        cap(page, "الاستبدال في نفس اللحظة: رصيد الإشعار 1.60 + كاش 11 لعصير 12")
        shot(page, "exchange-cart")
        fr.get_by_test_id("pay").click(); fr.get_by_test_id("receipt-modal").wait_for(); time.sleep(1.5)
        assert "1.60" in fr.get_by_test_id("receipt-sheet").inner_text(), "credit not shown on the sale receipt"
        shot(page, "exchange-sale-receipt", "فاتورة البيع الجديدة بعد الاستبدال", 800)
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        # a serial-numbered sale and a partial serial return
        fr.get_by_test_id("scan").fill("6230"); fr.get_by_test_id("scan").press("Enter"); time.sleep(1.5)
        fr.get_by_test_id("serial-input").fill("PH-1, PH-2"); time.sleep(1.5)
        fr.get_by_test_id("cash").fill("200"); time.sleep(1)
        cap(page, "بيع صنف بسيريال: السيريالات بتتكتب أو بتتمسح على السطر")
        shot(page, "serial-sale")
        fr.get_by_test_id("pay").click(); fr.get_by_test_id("receipt-modal").wait_for(); time.sleep(1.5)
        assert "PH-1" in fr.get_by_test_id("receipt-sheet").inner_text(), "serials missing on the receipt"
        shot(page, "serial-sale-receipt", None, 800)
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        fr.get_by_test_id("tab-returns").click(); time.sleep(0.5)
        fr.get_by_test_id("ret-search").fill("PH-1"); fr.get_by_test_id("ret-find").click(); time.sleep(2)
        fr.get_by_test_id("inv-row").first.click(); time.sleep(2)
        fr.get_by_test_id("serial-PH-1").check(); time.sleep(1)
        fr.get_by_test_id("mode-refund").check(); time.sleep(0.5)
        cap(page, "مرتجع جزئي: اختيار سيريال واحد (PH-1) واسترداد نقدي"); shot(page, "serial-return-pick")
        fr.get_by_test_id("ret-confirm").click(); fr.get_by_test_id("receipt-modal").wait_for(); time.sleep(1.5)
        rt = fr.get_by_test_id("receipt-sheet").inner_text()
        assert "100.00" in rt, "serial refund receipt: " + rt
        shot(page, "serial-return-receipt", "إيصال المرتجع (رجوع PH-1 فقط)", 800)
        fr.get_by_test_id("receipt-close").click(); time.sleep(0.5)
        fr.get_by_test_id("ret-search").fill("PH-1"); fr.get_by_test_id("ret-find").click(); time.sleep(2)
        fr.get_by_test_id("inv-row").first.click(); time.sleep(2)
        assert fr.get_by_test_id("serial-PH-1").count() == 0 and fr.get_by_test_id("serial-PH-2").count() == 1, "returned serial still offered"
        cap(page, "PH-1 اتسجل مرتجع ومش بيظهر تاني. PH-2 بس المتاح"); shot(page, "serial-return-blocked")
        fr.get_by_test_id("tab-sale").click(); time.sleep(1)
        # petty cash: the cashier takes 50 from the drawer for bags from the supermarket
        fr.get_by_test_id("cash-out").click(); fr.get_by_test_id("cm-amount").fill("50")
        cap(page, "عهدة: الكاشير بياخد 50 جنيه من الدرج. السبب إجباري"); shot(page, "pos-cashout-dialog", None, 500)
        fr.get_by_test_id("cm-save").click(); time.sleep(1.5)
        fr.get_by_test_id("cm-reason").fill("أكياس من السوبر ماركت") if fr.get_by_test_id("cm-reason").count() else None
        if fr.get_by_test_id("cm-save").count():
            fr.get_by_test_id("cm-save").click(); time.sleep(2)
        cap(page, "اتسجلت حركة السحب على الوردية"); shot(page, "pos-cashout-saved")
        fr.get_by_test_id("counted").fill("185.4")
        cap(page, "إغلاق الشيفت بالعد الفعلي للكاش")
        fr.get_by_test_id("close").click(); time.sleep(2)
        cap(page, "تقرير الإغلاق: المتوقع والفعلي والفرق")
        shot(page, "pos-z-report")
        zt = fr.get_by_test_id("z").inner_text()
        assert "0.00" in zt.split("/")[-1] and "185.40" in zt, "Z report does not balance: " + zt
    except Exception as e:
        log.append(("pos-flow", "FAIL " + str(e)[:200]))
        shot(page, "pos-flow-failure")

    # ---- manager approval of a blind close, then edit of an invoice in the closed shift
    try:
        pend = json.load(open("/tmp/orbit_pending.json"))
        go(page, "/app/orbit-pos"); time.sleep(3)
        fr = page.frame_locator("iframe")
        cap(page, "المدير: قفل شيفت بانتظار الاعتماد (الكاشير قفل أعمى)")
        fr.get_by_test_id("approvals").wait_for(timeout=20000)
        shot(page, "web-approvals-list")
        fr.get_by_test_id("approvals").locator("button").first.click(); time.sleep(2)
        fr.get_by_test_id("cv-expected").wait_for(timeout=20000)
        txt = fr.get_by_test_id("close-view").inner_text()
        assert "110" in txt and "-2" in txt.replace(" ", ""), "expected/diff not shown to manager: " + txt
        cap(page, "المدير يشوف المتوقع والمقفول بيه والفرق قبل الاعتماد")
        shot(page, "web-approve-view")
        fr.get_by_test_id("cv-note").fill("فرق بسيط، تمت المراجعة")
        fr.get_by_test_id("cv-approve").click(); time.sleep(2)
        fr.get_by_test_id("approved-z").wait_for(timeout=20000)
        cap(page, "تم اعتماد القفل")
        shot(page, "web-approved")
        fr.get_by_test_id("ed-q").fill(pend["invoice"]); fr.get_by_test_id("ed-search").click(); time.sleep(2)
        fr.get_by_test_id("ed-pick-" + pend["invoice"]).click(); time.sleep(2)
        fr.get_by_test_id("ed-closed").wait_for(timeout=20000)
        cap(page, "الفاتورة في شيفت مقفول: لازم إلغاء القفل الأول")
        shot(page, "web-edit-closed")
        fr.get_by_test_id("ed-reason-reopen").fill("تصحيح كمية"); fr.get_by_test_id("ed-reopen").click(); time.sleep(3)
        fr.get_by_test_id("ed-form").wait_for(timeout=20000)
        cap(page, "بعد إلغاء القفل: تعديل الدفع وتسجيل السبب")
        shot(page, "web-edit-form")
        fr.get_by_test_id("ed-card").fill("12"); fr.get_by_test_id("ed-cash").fill("0")
        fr.get_by_test_id("ed-ref").fill("AUTH-778899")
        fr.get_by_test_id("ed-reason").fill("العميل دفع كارت")
        fr.get_by_test_id("ed-save").click(); time.sleep(3)
        fr.get_by_test_id("receipt-modal").wait_for(timeout=20000)
        rt = fr.get_by_test_id("receipt-sheet").inner_text()
        assert "AUTH-778899" in rt, "card reference missing on the revised receipt: " + rt[:300]
        cap(page, "اتعملت نسخة معدّلة مرتبطة بالأصل"); shot(page, "web-edit-saved")
    except Exception as e:
        log.append(("approve-edit-flow", "FAIL " + str(e)[:300]))
        shot(page, "approve-edit-failure")

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
bad = [x for x in log if (len(x) == 2 and str(x[1]).startswith("FAIL")) or x[0] == "api"]
if bad:
    print("CAPTURE FAILED:", bad); sys.exit(1)
