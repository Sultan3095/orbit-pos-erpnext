# Orbit POS for ERPNext

A full point of sale that runs inside ERPNext (v15 and v16): a React cashier screen, and every sale,
return, shift and approval lands in the ERPNext database in real time. Arabic RTL and English UI.

Status: installed and tested on real ERPNext v15 and v16 sites by CI on every push
(`.github/workflows/erpnext-ci.yml`): 61 integration tests per version plus two-terminal concurrency
races (gift card, coupon, exchange receipt, duplicate-retry) and full UI screenshot captures.

## What is here
- `orbit_pos/logic/`: pure Python rules (promotions incl. "buy 2 get 3", EAN-13 and scale barcodes,
  returns window + pro-rata refund + cross-branch toggle, loyalty, offline idempotency).
- `orbit_pos/orbit_pos/doctype/`: POS Shift (one open shift per user, optional shared shift, blind close
  with second-manager approval over a threshold), POS Cash Movement, POS Promotion (+ day table),
  Offline Transaction (unique txn id), POS Manager Approval, POS Recount, POS Gift Card (+ Log),
  POS Coupon, POS Exchange Receipt (one-time use), POS Payment Attempt, POS ETA Receipt,
  Loyalty Ledger Entry, Orbit POS Settings.
- `orbit_pos/api/`: shift, sales (quote, submit_sale, returns), purchase_import (Excel, all-or-nothing),
  gifts (gift cards + coupons), exchange receipts, recounts, approvals, provider payments, ETA, reports.
- `frontend/`: React UI (Arabic RTL / English, light/dark/Orbit/galaxy themes, split cash+card,
  3*barcode, offline queue, customer screen at `#display`). Build output goes to `orbit_pos/public/pos`.

## Provider payments and ETA e-receipts
Paymob and Fawry payments and Egyptian ETA e-receipts are implemented with three modes in Orbit POS
Settings: off, mock (for training), live. The mock mode is built from the providers' published docs and
is what CI tests against. Live mode needs your official keys (keep them in a vault, never in chat);
it has not been run against the real services yet.

## Install on a bench
    bench get-app /path/to/orbit_pos
    bench --site yoursite install-app orbit_pos
    bench --site yoursite migrate
    cd apps/orbit_pos/frontend && npm install && npm run build && cd - && bench build --app orbit_pos
Then: give users the "POS User"/"POS Manager" roles, set each manager's POS PIN (User form), create an
ERPNext POS Profile (with Cash and Credit Card modes of payment), open `/app/orbit-pos` (v15) or
`/desk/orbit-pos` (v16 moved the desk from /app to /desk).

## Run the tests
    python3 -m unittest discover -s tests -t .          # logic + import parser
    cd frontend && npm test && npm run build            # UI unit tests + build
Full integration (needs a bench): the CI workflow installs ERPNext v15 and v16 on GitHub's runners and
runs `orbit_pos/tests/test_flows.py` (61 tests), the concurrency script, and `tools/capture.py`
(screenshots + walkthrough video, Arabic and English) on each version.

## Not verified yet
- Real hardware (barcode scanner, receipt printer, customer display): works in the browser/e2e tests,
  not yet tried on physical devices.
- Live Paymob/Fawry/ETA credentials: tested only against the mocks built from their docs.

## License

GPL-3.0-or-later (see LICENSE). Orbit POS is open source. The web app matches the GPL used by Frappe/ERPNext. The business model is support, hosting and customization, not license sales.

---

# Orbit POS لـ ERPNext

برنامج كاشير كامل يشتغل جوه ERPNext (إصدار 15 و16): شاشة كاشير React، وكل عملية بيع ومرتجع وشيفت
واعتماد بتتسجل في قاعدة بيانات ERPNext لحظياً. واجهة عربي RTL وإنجليزي.

الحالة: بيتثبت ويتختبر على مواقع ERPNext حقيقية v15 وv16 في CI مع كل رفع
(`.github/workflows/erpnext-ci.yml`): 61 اختبار تكامل لكل إصدار، بالإضافة لاختبارات تزامن بين
جهازين (كارت هدية، كوبون، إيصال استبدال، إعادة إرسال مكررة)، ولقطات شاشة كاملة للواجهة.

## الموجود هنا
- `orbit_pos/logic/`: قواعد Python خالصة (العروض بما فيها "اشترِ 2 وخد 3"، باركود EAN-13 والميزان،
  مدة المرتجع + رد بنسبة المدفوع + خيار المرتجع بين الفروع، الولاء، منع تكرار العمليات أوفلاين).
- `orbit_pos/orbit_pos/doctype/`: شيفت POS (شيفت مفتوح واحد لكل مستخدم، شيفت مشترك اختياري، قفل مغمض
  مع اعتماد مدير ثانٍ فوق حد معين)، حركة كاش POS، عرض POS (+ جدول الأيام)، عملية أوفلاين
  (رقم فريد لكل عملية)، اعتماد مدير POS، جرد POS، كارت هدية POS (+ سجل)، كوبون POS،
  إيصال استبدال POS (يُستخدم مرة واحدة)، محاولة دفع POS، إيصال ضريبي ETA، سجل نقاط الولاء،
  إعدادات Orbit POS.
- `orbit_pos/api/`: الشيفتات، المبيعات (تسعير، تنفيذ، مرتجعات)، استيراد المشتريات (إكسل، الكل أو لا شيء)،
  الهدايا (كروت + كوبونات)، إيصالات الاستبدال، الجرد، الاعتمادات، الدفع الإلكتروني، ETA، التقارير.
- `frontend/`: واجهة React (عربي RTL / إنجليزي، ثيمات فاتح/غامق/Orbit/جالاكسي، دفع مقسّم كاش+كارت،
  3*باركود، طابور أوفلاين، شاشة عميل على `#display`). ناتج البناء يذهب إلى `orbit_pos/public/pos`.

## الدفع الإلكتروني والإيصالات الضريبية ETA
مدفوعات Paymob وفوري والإيصالات الضريبية المصرية ETA منفَّذة بثلاث حالات في إعدادات Orbit POS:
مقفول، تجريبي (mock، للتدريب)، حقيقي (live). الوضع التجريبي مبني على مستندات الشركات المنشورة وهو
اللي بيتختبر عليه في CI. الوضع الحقيقي محتاج مفاتيحك الرسمية (تحفظها في خزنة آمنة، أبداً في الشات)؛
ولم يتم تشغيله على الخدمات الحقيقية بعد.

## التثبيت على bench
    bench get-app /path/to/orbit_pos
    bench --site yoursite install-app orbit_pos
    bench --site yoursite migrate
    cd apps/orbit_pos/frontend && npm install && npm run build && cd - && bench build --app orbit_pos
بعدها: امنح المستخدمين دورَي "POS User"/"POS Manager"، وعيّن الرقم السري لكل مدير (من نموذج User)،
وأنشئ POS Profile في ERPNext (بطريقتي دفع Cash وCredit Card)، وافتح `/app/orbit-pos` (في v15) أو
`/desk/orbit-pos` (في v16 نُقل الـ desk من /app إلى /desk).

## تشغيل الاختبارات
    python3 -m unittest discover -s tests -t .          # المنطق + محلل الاستيراد
    cd frontend && npm test && npm run build            # اختبارات الواجهة + البناء
التكامل الكامل (محتاج bench): سير عمل CI بيثبت ERPNext v15 وv16 على خوادم GitHub ويشغّل
`orbit_pos/tests/test_flows.py` (61 اختباراً)، وسكربت التزامن، و`tools/capture.py`
(لقطات شاشة + فيديو جولة، عربي وإنجليزي) على كل إصدار.

## لم يتم التأكد منه بعد
- الأجهزة الحقيقية (قارئ الباركود، طابعة الإيصالات، شاشة العميل): تعمل في اختبارات المتصفح،
  ولم تُجرَّب على أجهزة فعلية بعد.
- مفاتيح Paymob/فوري/ETA الحقيقية: تم الاختبار فقط على المحاكيات المبنية من مستنداتهم.

## الرخصة

GPL-3.0-or-later (انظر LICENSE). Orbit POS مفتوح المصدر. تطبيق الويب على نفس رخصة GPL المستخدمة في Frappe/ERPNext. النموذج التجاري هو الدعم والاستضافة والتخصيص، وليس بيع التراخيص.
