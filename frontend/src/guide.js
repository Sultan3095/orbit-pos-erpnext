/* Guide mascot ("Captain Orbit") for the web POS: a cartoon man in a suit who shows up when something is wrong or missing,
   POINTS at the exact control, says a short line, explains when tapped, and can be dismissed. Once per issue per user. */
const L = (ar, en) => ({ ar, en });
export const ISSUES = {
  EMPTY_CART: { sel: ['[data-testid=scan]'], short: L('السلة فاضية. ضيف صنف الأول.', 'The cart is empty. Add an item first.'), long: L('اسكن الباركود أو اكتب اسم الصنف في الخانة دي وادوس Enter. بعد ما الصنف يظهر في السلة دوس دفع.', 'Scan the barcode or type the item code here and press Enter. When the item shows in the cart press Pay.') },
  NOT_FOUND: { sel: ['[data-testid=scan]'], short: L('الصنف مش موجود.', 'Item not found.'), long: L('راجع الباركود أو الكود. لو الصنف جديد لازم يتضاف في ERPNext الأول.', 'Check the barcode or code. If the item is new it must be added in ERPNext first.') },
  UNDERPAID: { sel: ['[data-testid=cash]'], short: L('المدفوع أقل من الإجمالي.', 'The payment is less than the total.'), long: L('اكتب المبلغ المستلم في خانة الكاش، أو وزّع المبلغ بين الكاش والكارت. لما المتبقي يبقى صفر دوس دفع.', 'Type the cash received here, or split the amount between cash and card. When Remaining is zero press Pay.') },
  SERIALS: { sel: ['[data-testid=serial-input]'], short: L('ناقص أرقام سيريال.', 'Serial numbers are missing.'), long: L('الصنف ده بيتباع بسيريال. اكتب سيريال لكل قطعة، بعدد الكمية بالظبط.', 'This item is sold by serial number. Enter one serial per unit, exactly as many as the quantity.') },
  NO_SHIFT: { sel: ['[data-testid=open]'], short: L('مفيش شيفت مفتوح.', 'There is no open shift.'), long: L('اكتب الكاش اللي في الدرج واضغط فتح شفت عشان تقدر تبيع.', 'Enter the cash in the drawer and press Open shift so you can sell.') },
  GIFT: { sel: ['[data-testid=gift-no]'], short: L('في مشكلة في كارت الهدية.', 'There is a problem with the gift card.'), long: L('راجع رقم الكارت. الكارت لازم يكون مباع، مش منتهي ولا ملغي ولا فاضي. تقدر تستعلم عن حالته من تبويب كروت الهدايا.', 'Check the card number. The card must be sold, not expired, void or empty. You can look up its state on the Gift cards tab.') },
  COUPON: { sel: ['[data-testid=coupon-code]'], short: L('الكوبون مش مقبول.', 'The coupon was not accepted.'), long: L('الكوبون ممكن يكون منتهي أو مقفول أو الفاتورة أقل من الحد الأدنى، أو محتاج عميل محدد. راجع الكوبون من تبويب الكوبونات.', 'The coupon may be expired, switched off, the invoice may be under its minimum, or it needs a named customer. Review it on the Coupons tab.') },
  REASON: { sel: ['[data-testid=cm-reason]', '[data-testid=ed-reason]', '[data-testid=ed-reason-reopen]', '[data-testid=gw-reason]'], short: L('السبب ناقص.', 'The reason is missing.'), long: L('اكتب السبب (3 حروف على الأقل). بيتسجل في سجل المراجعة.', 'Write the reason (3+ characters). It is saved in the audit log.') },
  COUNTED: { sel: ['[data-testid=counted]'], short: L('اكتب الكاش اللي عديته.', 'Enter the cash you counted.'), long: L('عدّ الكاش اللي في الدرج واكتب المبلغ هنا قبل ما تقفل الشيفت. القفل أعمى: مش هتشوف المتوقع.', 'Count the cash in the drawer and type the amount here before closing the shift. The close is blind: you will not see the expected amount.') },
  REJECTED: { sel: ['[data-testid=rejected]'], short: L('في عملية بيع اتقفلت ومتسجلتش.', 'A sale was refused and NOT recorded.'), long: L('العميل دفع لكن السيرفر رفض الفاتورة (مثلا الشيفت اتقفل أو السعر اتغير). اقرا السبب في المستطيل الأحمر، وبلّغ المدير. بعد حل السبب دوس إعادة المحاولة، أو تجاهل لو اتسجلت بطريقة تانية.', 'The customer paid but the server refused the invoice (for example the shift was closed or a price changed). Read the reason in the red box and tell the manager. After the cause is fixed press Retry, or Dismiss if it was recorded another way.') },
  OFFLINE_PROMO: { sel: ['[data-testid=pay-wrap]'], short: L('مفيش نت والعروض مش هتتحسب.', 'Offline: offers cannot be calculated.'), long: L('في عرض أو كوبون ممكن ينطبق على السلة، ومفيش اتصال فمش هينفع نحسب الإجمالي الصح. استنى الاتصال يرجع، أو شيل الأصناف اللي عليها عرض.', 'An offer or coupon may apply to this cart and there is no connection, so the right total cannot be calculated. Wait for the connection, or remove the items that have an offer.') },
};
let cur = null;
  function mascotSVG() {
    return '<svg viewBox="0 0 120 170" width="104" height="147" xmlns="http://www.w3.org/2000/svg">' +
      '<ellipse cx="60" cy="164" rx="34" ry="5" fill="#000" opacity=".18"/>' +
      '<rect x="38" y="112" width="18" height="48" rx="6" fill="#12284C"/><rect x="64" y="112" width="18" height="48" rx="6" fill="#12284C"/><rect x="34" y="156" width="26" height="9" rx="4" fill="#000"/><rect x="60" y="156" width="26" height="9" rx="4" fill="#000"/>' +
      '<path d="M30 62 Q30 52 44 50 L76 50 Q90 52 90 62 L92 118 L28 118 Z" fill="#12284C"/>' +
      '<path d="M50 50 L60 78 L70 50 Z" fill="#fff"/><path d="M57 60 L63 60 L66 100 L60 108 L54 100 Z" fill="#F2A93B"/>' +
      '<path d="M44 50 L58 76 L46 82 L36 60 Z" fill="#1BA39C" opacity=".9"/><path d="M76 50 L62 76 L74 82 L84 60 Z" fill="#1BA39C" opacity=".9"/>' +
      '<g id="g-arm" transform="rotate(0 84 62)"><rect x="82" y="56" width="40" height="12" rx="6" fill="#12284C"/><circle cx="124" cy="62" r="7.5" fill="#F3C9A0"/><rect x="124" y="59" width="12" height="5" rx="2.5" fill="#F3C9A0"/></g>' +
      '<rect x="14" y="62" width="16" height="44" rx="8" fill="#12284C"/><circle cx="22" cy="110" r="7" fill="#F3C9A0"/>' +
      '<circle cx="60" cy="30" r="23" fill="#F3C9A0"/><path d="M37 28 Q38 6 60 6 Q82 6 83 28 Q72 16 60 18 Q48 16 37 28 Z" fill="#2b1d12"/>' +
      '<circle cx="51" cy="31" r="3" fill="#222"/><circle cx="69" cy="31" r="3" fill="#222"/><path d="M52 41 Q60 47 68 41" stroke="#8a4b2a" stroke-width="2.5" fill="none" stroke-linecap="round"/>' +
      '<path d="M46 24 Q51 21 56 24 M64 24 Q69 21 74 24" stroke="#2b1d12" stroke-width="2" fill="none"/></svg>';
  }
  function ensureCss() {
    if (document.getElementById('guide-css')) return;
    const s = document.createElement('style'); s.id = 'guide-css';
    s.textContent = '#guide{position:fixed;inset:0;z-index:100000;pointer-events:none}#guide *{pointer-events:auto}#guide .gring{position:fixed;border:3px solid #F2A93B;border-radius:10px;box-shadow:0 0 0 4px rgba(242,169,59,.28),0 0 18px rgba(242,169,59,.8);pointer-events:none;animation:gpulse 1.1s ease-in-out infinite}' +
      '@keyframes gpulse{50%{box-shadow:0 0 0 9px rgba(242,169,59,.15),0 0 26px rgba(242,169,59,1)}}#guide .gbox{position:fixed;display:flex;align-items:flex-end;gap:6px;max-width:440px}#guide .gman{cursor:pointer;flex:none;filter:drop-shadow(0 6px 10px rgba(0,0,0,.35));transition:transform .15s}#guide .gman:hover{transform:scale(1.04)}' +
      '#guide .gbub{background:#fff;color:#12284C;border:2px solid #1BA39C;border-radius:14px;padding:10px 12px;font:600 14px/1.5 "Segoe UI",Tahoma,Arial,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.3);min-width:180px}#guide .gbub small{display:block;font-weight:400;margin-top:6px;opacity:.85}' +
      '#guide .gbub .gx{float:inline-end;border:0;background:#eef2f7;border-radius:8px;cursor:pointer;margin-inline-start:8px;padding:2px 8px;color:#12284C}#guide .gbub .gok{margin-top:8px;border:0;background:#1BA39C;color:#fff;border-radius:8px;padding:5px 12px;cursor:pointer;font-weight:600}#guide .gtap{color:#1BA39C;font-weight:600;font-size:12px}';
    document.head.appendChild(s);
  }
  function close() { const g = document.getElementById('guide'); if (g) g.remove(); cur = null; }
const find = (sels) => { for (const s of sels) { const all = [...document.querySelectorAll(s)].filter((x) => x.offsetParent !== null); const e = s === '.msg' ? all[all.length - 1] : all[0]; if (e && e.offsetParent !== null) return e; } return null; };
const keyOf = (u, k) => 'orbit_guide_seen:' + (u || '') + ':' + k;
export const guideOff = (user) => localStorage.getItem('orbit_guide_off:' + (user || '')) === '1';
export const setGuideOff = (user, off) => { localStorage.setItem('orbit_guide_off:' + (user || ''), off ? '1' : '0'); if (off) close(); else Object.keys(localStorage).filter((k) => k.startsWith('orbit_guide_seen:' + (user || '') + ':')).forEach((k) => localStorage.removeItem(k)); };
export const closeGuide = close;
export function showGuide(key, { lang, user, force, issue } = {}) {
  const I = issue || ISSUES[key]; if (!I) return false;
  if (!force && (guideOff(user) || localStorage.getItem(keyOf(user, key)))) return false;
  setTimeout(() => {
    const target = find(I.sel); if (!target) return;
    ensureCss(); close();
    try { target.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
    const lg = lang === 'en' ? 'en' : 'ar'; const tx = (o) => o[lg];
    const r = target.getBoundingClientRect(); const W = window.innerWidth, H = window.innerHeight;
    const g = document.createElement('div'); g.id = 'guide'; g.setAttribute('data-guide', key); g.dir = lg === 'ar' ? 'rtl' : 'ltr';
    const ring = document.createElement('div'); ring.className = 'gring'; Object.assign(ring.style, { left: r.left - 5 + 'px', top: r.top - 5 + 'px', width: r.width + 10 + 'px', height: r.height + 10 + 'px' });
    const box = document.createElement('div'); box.className = 'gbox'; box.style.direction = 'ltr';
    const hw = 104, hh = 147;
    const below = r.bottom + hh + 20 < H; const top = below ? r.bottom + 18 : Math.max(8, r.top - hh - 18);
    const toRight = (W - r.right) > r.left; let left = toRight ? Math.min(r.left, W - hw - 260) : Math.max(8, r.right - hw - 260);
    left = Math.max(8, Math.min(left, W - hw - 200));
    box.style.left = left + 'px'; box.style.top = top + 'px';
    box.innerHTML = '<div class="gman" title="' + (lg === 'ar' ? 'دوس عليّ للشرح' : 'Tap me for the details') + '">' + mascotSVG() + '</div><div class="gbub"><button class="gx" data-g="x" aria-label="close">✕</button><div data-g="short">' + tx(I.short) + '</div><span class="gtap" data-g="tap">' + (lg === 'ar' ? 'دوس عليّ للشرح' : 'Tap me to see how to fix it') + '</span></div>';
    g.appendChild(ring); g.appendChild(box); document.body.appendChild(g);
    const man = box.querySelector('.gman svg').getBoundingClientRect(); const px = man.left + 84 / 120 * man.width, py = man.top + 62 / 170 * man.height;
    const ang = Math.atan2(r.top + r.height / 2 - py, r.left + r.width / 2 - px) * 180 / Math.PI;
    box.querySelector('#g-arm').setAttribute('transform', 'rotate(' + ang.toFixed(1) + ' 84 62)');
    const done = () => { if (!force) localStorage.setItem(keyOf(user, key), '1'); close(); };
    const explain = () => { const b = box.querySelector('.gbub'); b.innerHTML = '<button class="gx" data-g="x" aria-label="close">✕</button><div>' + tx(I.short) + '</div><small data-g="long">' + tx(I.long) + '</small><button class="gok" data-g="ok">' + (lg === 'ar' ? 'تمام، فهمت' : 'Got it') + '</button>'; };
    g.addEventListener('click', (e) => { const d = e.target.closest('[data-g]'); if (e.target.closest('.gman') || (d && d.dataset.g === 'tap')) return explain(); if (d && (d.dataset.g === 'x' || d.dataset.g === 'ok')) done(); });
    cur = key;
  }, 120);
  return true;
}

// ---- Any error: the Captain appears, points at the message and explains it in plain words.
// Known server messages get a specific Arabic line and a "what to do" step; anything else gets the message itself
// plus a generic next step, so no error is ever shown without him.
export const ctx = { lang: 'ar', user: '' };
const E = (re, ar, arLong, en, enLong) => ({ re, ar, arLong, en, enLong });
const PATTERNS = [
  E(/may not change prices|price of .* is/i, 'السعر مختلف عن قائمة الأسعار.', 'سعر الصنف على الشاشة غير سعره في قائمة الأسعار، وصلاحيتك لا تسمح بتغيير السعر. امسح الصنف من جديد، أو اطلب من المدير يغيّر السعر.', 'The price differs from the price list.', 'The price on screen is not the price list price and your role may not change prices. Scan the item again or ask a manager.'),
  E(/Shift is not open|no open shift|Open a shift/i, 'مفيش شيفت مفتوح.', 'لازم يكون عندك شيفت مفتوح عشان البيع أو المرتجع. افتح شيفت الأول بالكاش اللي في الدرج.', 'There is no open shift.', 'You need an open shift to sell or return. Open one first with the cash in the drawer.'),
  E(/belongs to another user/i, 'الشيفت ده بتاع مستخدم تاني.', 'مينفعش تشتغل على شيفت مستخدم تاني. افتح شيفتك أو اطلب من المدير.', 'This shift belongs to another user.', 'You cannot work on another user\'s shift. Open your own or ask a manager.'),
  E(/Not permitted|may not|not a POS Manager|cannot approve/i, 'مش مسموح لك بالعملية دي.', 'صلاحيتك مش بتسمح بالخطوة دي. اطلب من المدير ينفذها أو يديك موافقة بالرقم السري.', 'This is not allowed for your role.', 'Your role cannot do this step. Ask a manager to do it or to approve it with his PIN.'),
  E(/Manager approval required|Wrong manager PIN/i, 'محتاج موافقة المدير.', 'اكتب اسم المدير ورقمه السري الصح في الخانتين اللي ظهروا.', 'A manager approval is needed.', 'Type the manager user and his correct PIN in the two fields shown.'),
  E(/less than total/i, 'المدفوع أقل من الإجمالي.', 'المبلغ المدفوع لا يغطي إجمالي الفاتورة. زوّد الكاش أو الكارت لحد ما المتبقي يبقى صفر.', 'The payment is less than the total.', 'The amount paid does not cover the invoice. Add cash or card until Remaining is zero.'),
  E(/not on this POS Profile|amount must be more than zero/i, 'طريقة الدفع غير صحيحة.', 'طريقة الدفع غير موجودة في ملف نقطة البيع أو مبلغها صفر. استخدم كاش أو كارت بمبلغ أكبر من صفر.', 'The payment method is not valid.', 'The method is not on the POS Profile or its amount is zero. Use cash or card with an amount above zero.'),
  E(/Exchange receipt .* (is already|not found|expired)/i, 'إيصال الاستبدال مش صالح.', 'الإيصال ده اتستخدم قبل كده أو منتهي أو رقمه غلط. الإيصال بيتستخدم مرة واحدة بس.', 'The exchange receipt is not usable.', 'It was already used, has expired or the number is wrong. An exchange receipt works only once.'),
  E(/Too many wrong gift card/i, 'محاولات كتير غلط.', 'اتكتب رقم كارت هدية غلط أكتر من مرة. استنى كام دقيقة وجرب بالرقم الصح من الكارت نفسه.', 'Too many wrong tries.', 'Too many wrong gift card numbers. Wait a few minutes and try the number printed on the card.'),
  E(/named customer to use loyalty/i, 'اختار عميل بالاسم.', 'نقاط الولاء بتتصرف لعميل بالاسم بس، مش للعميل النقدي. اختار العميل الأول.', 'Choose a named customer.', 'Loyalty points belong to a named customer, not the cash customer. Pick the customer first.'),
  E(/already have an open shift/i, 'عندك شيفت مفتوح بالفعل.', 'مينفعش تفتح شيفتين. كمّل على الشيفت المفتوح أو اقفله الأول.', 'You already have an open shift.', 'You cannot open two shifts. Continue on the open one or close it first.'),
  E(/needs? a named customer|coupon/i, 'الكوبون مش مقبول.', 'الكوبون ممكن يكون منتهي أو مقفول أو الفاتورة أقل من الحد الأدنى أو محتاج عميل محدد.', 'The coupon was not accepted.', 'It may be expired, off, the invoice may be under its minimum, or it needs a named customer.'),
  E(/gift card/i, 'في مشكلة في كارت الهدية.', 'راجع رقم الكارت. لازم يكون مباع وغير منتهي وغير ملغي وفيه رصيد.', 'There is a problem with the gift card.', 'Check the number. The card must be sold, not expired, not cancelled and have a balance.'),
  E(/needed|insufficient|not enough stock|negative stock/i, 'المخزون مش كفاية.', 'الكمية المطلوبة أكبر من الموجود في المخزن. قلل الكمية أو استلم بضاعة في ERPNext.', 'Not enough stock.', 'The quantity is more than what is on hand. Lower it or receive stock in ERPNext.'),
  E(/Item not found/i, 'الصنف مش موجود.', 'راجع الباركود أو الكود. لو الصنف جديد لازم يتضاف في ERPNext الأول.', 'Item not found.', 'Check the barcode or code. A new item must be added in ERPNext first.'),
  E(/after the window|window/i, 'الفاتورة خارج مدة المرتجع.', 'المرتجع بعد المدة المسموحة يحتاج موافقة المدير.', 'The invoice is outside the return window.', 'A return after the allowed days needs a manager approval.'),
  E(/Reason|reason/, 'السبب ناقص.', 'اكتب السبب (3 حروف على الأقل). بيتسجل في سجل المراجعة.', 'The reason is missing.', 'Write the reason (3+ characters). It is saved in the audit log.'),
  E(/Server error|network|Failed to fetch|offline/i, 'مفيش اتصال بالسيرفر.', 'الاتصال بالسيرفر وقع. العمليات بتتحفظ على الجهاز وهتتبعت لوحدها لما الاتصال يرجع.', 'The server cannot be reached.', 'The connection dropped. Sales are saved on this device and are sent automatically when it is back.'),
];
export function explain(m) {
  const msg = String(m || '');
  const hit = PATTERNS.find((p) => p.re.test(msg));
  const unknownAr = 'حصلت مشكلة. اقرا الرسالة اللي ظهرت. لو اتكررت صوّر الشاشة وابعتها للمدير.';
  const unknownEn = 'Something went wrong. Read the message shown. If it repeats, take a screenshot and send it to the manager.';
  return { sel: ['.msg', '[data-testid=msg]', 'header'],
    short: L(hit ? hit.ar : 'حصلت مشكلة.', hit ? hit.en : 'Something went wrong.'),
    long: L((hit ? hit.arLong : unknownAr) + '\n' + msg, (hit ? hit.enLong : unknownEn) + '\n' + msg) };
}
/** Use in place of `setMsg(e.message)`: shows the Captain with the explanation and returns the message text. */
export function fail(e) {
  const m = (e && e.message) || String(e || '');
  showGuide('ERROR', { ...ctx, force: true, issue: explain(m) });
  return m;
}
