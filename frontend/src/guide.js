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
const find = (sels) => { for (const s of sels) { const e = document.querySelector(s); if (e && e.offsetParent !== null) return e; } return null; };
const keyOf = (u, k) => 'orbit_guide_seen:' + (u || '') + ':' + k;
export const guideOff = (user) => localStorage.getItem('orbit_guide_off:' + (user || '')) === '1';
export const setGuideOff = (user, off) => { localStorage.setItem('orbit_guide_off:' + (user || ''), off ? '1' : '0'); if (off) close(); else Object.keys(localStorage).filter((k) => k.startsWith('orbit_guide_seen:' + (user || '') + ':')).forEach((k) => localStorage.removeItem(k)); };
export const closeGuide = close;
export function showGuide(key, { lang, user, force } = {}) {
  const I = ISSUES[key]; if (!I) return false;
  if (!force && (guideOff(user) || localStorage.getItem(keyOf(user, key)))) return false;
  setTimeout(() => {
    const target = find(I.sel); if (!target) return;
    ensureCss(); close();
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
