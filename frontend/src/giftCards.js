import JsBarcode from 'jsbarcode';
import qrcode from 'qrcode-generator';

// Printable gift cards: 85.6 x 54 mm, 8 per A4 page, plus one back page. The QR code and the Code 128 barcode both carry the card number.
const esc = (x) => String(x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function qrSvg(text, px = 110) {
  const q = qrcode(0, 'M'); q.addData(String(text)); q.make();
  const n = q.getModuleCount(); let d = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `<rect x="${c}" y="${r}" width="1.02" height="1.02"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${px}" height="${px}" viewBox="0 0 ${n} ${n}" fill="#12284C" shape-rendering="crispEdges">${d}</svg>`;
}
export function barSvg(text) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  JsBarcode(svg, text, { format: 'CODE128', height: 40, width: 2, displayValue: false, margin: 0 });
  return svg.outerHTML.replace('<svg ', '<svg style="width:280px;height:42px" preserveAspectRatio="none" ');
}
const MARK = '<svg width="70" height="70" viewBox="0 0 120 120"><circle cx="60" cy="60" r="22" fill="#fff"/><ellipse cx="60" cy="60" rx="52" ry="22" fill="none" stroke="#1BA39C" stroke-width="7" transform="rotate(-25 60 60)"/><circle cx="104" cy="40" r="9" fill="#F2A93B"/></svg>';
const front = (c, store, cur) => `<div class="gcell"><div class="gcard" style="background:linear-gradient(135deg,#12284C,#0d1d38);color:#fff"><div class="gtop"><div class="gbrand">${MARK}<b>ORBIT</b></div><div class="ggc">بطاقة هدية<br><span>GIFT CARD</span></div></div>
<div class="gval" style="color:${c.value >= 1000 ? '#1BA39C' : '#F2A93B'}">${esc(Number(c.value).toLocaleString('en-US'))}<small> ${esc(cur)}</small></div>
<div class="gmid"><div class="gqr">${qrSvg(c.card_no)}</div><div><div class="glab">رقم البطاقة · Card No.</div><div class="gno">${esc(c.card_no)}</div><div class="gbar">${barSvg(c.card_no)}</div></div></div><div class="gfoot">${esc(store)}</div></div></div>`;
const back = (store) => `<div class="gcell"><div class="gcard" style="background:#F1F5F9;color:#12284C"><div style="height:70px;background:#12284C"></div><div style="direction:rtl;padding:26px 40px;font-size:19px;line-height:1.7"><b style="font-size:23px">الشروط · Terms</b><br>• البطاقة لحاملها وتُستخدم كوسيلة دفع على المشتريات من المحل.<br>• لا تُستبدل بنقد. الرصيد المتبقي يبقى على البطاقة.<br>• الاحتفاظ بالبطاقة مسؤولية حاملها.<br><span dir="ltr" style="display:block;margin-top:6px">• Redeemable in store as a payment method. Not exchangeable for cash. Remaining balance stays on the card.</span></div>
<div style="position:absolute;bottom:22px;left:40px;right:40px;font-size:17px;display:flex;justify-content:space-between"><span>${esc(store)}</span><span>توقيع / Signature: ____________</span></div></div></div>`;
export const SHEET_CSS = '*{box-sizing:border-box;margin:0}.pg{width:210mm;height:297mm;padding:31mm 15.4mm 0;display:grid;grid-template-columns:85.6mm 85.6mm;grid-auto-rows:54mm;gap:6mm 8mm;page-break-after:always;direction:ltr;background:#fff}.pg.back{direction:rtl}' +
  '.gcell{width:85.6mm;height:54mm;outline:.2mm dashed #999;outline-offset:.6mm;overflow:hidden;border-radius:3mm}.gcard{zoom:.378;width:856px;height:540px;position:relative;overflow:hidden;-webkit-print-color-adjust:exact;print-color-adjust:exact}' +
  '.gtop{display:flex;justify-content:space-between;padding:36px 44px;direction:ltr;align-items:flex-start}.gbrand{display:flex;align-items:center;gap:14px;font-size:34px;letter-spacing:6px}.ggc{text-align:right;font-size:26px}.ggc span{font-size:16px;letter-spacing:4px;opacity:.7}' +
  '.gval{font-size:120px;font-weight:800;padding:0 44px;direction:ltr;line-height:1}.gval small{font-size:28px;color:#fff;font-weight:400}.gmid{position:absolute;left:44px;right:44px;bottom:70px;display:flex;gap:26px;align-items:flex-end;direction:ltr}.gqr{background:#fff;padding:8px;border-radius:12px;line-height:0}' +
  '.glab{font-size:17px;opacity:.75;margin-bottom:6px}.gno{font-size:34px;letter-spacing:4px;font-family:Consolas,"DejaVu Sans Mono",monospace;margin-bottom:10px}.gbar{background:#fff;padding:6px 10px;border-radius:8px;display:inline-block;line-height:0}.gfoot{position:absolute;bottom:20px;left:0;right:0;text-align:center;font-size:17px;opacity:.7}';
export function sheetBody(cards, store, cur) {
  const pages = []; for (let i = 0; i < cards.length; i += 8) pages.push(cards.slice(i, i + 8));
  return pages.map((p) => `<div class="pg">${p.map((c) => front(c, store, cur)).join('')}</div>`).join('') +
    `<div class="pg back">${Array(Math.min(8, cards.length)).fill(back(store)).join('')}</div>`;
}
export function printSheet(cards, store, cur) {
  const w = window.open('', '_blank'); if (!w) return false;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Gift cards</title><style>@page{size:A4;margin:0}body{font-family:"Segoe UI","Noto Sans Arabic",Tahoma,Arial,sans-serif}${SHEET_CSS}</style></head><body>${sheetBody(cards, store, cur)}</body></html>`);
  w.document.close(); setTimeout(() => w.print(), 400); return true;
}
