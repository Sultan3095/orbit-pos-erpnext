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
const giftIcon = (acc, w, extra, ink) => { ink = ink || '#fff'; return '<svg class="gicon" width="' + w + '" height="' + w + '" viewBox="0 0 200 200" style="' + (extra || '') + '"><rect x="36" y="94" width="128" height="86" rx="8" fill="' + ink + '" fill-opacity=".16" stroke="' + ink + '" stroke-opacity=".55" stroke-width="4"/><rect x="26" y="68" width="148" height="30" rx="8" fill="' + ink + '" fill-opacity=".24" stroke="' + ink + '" stroke-opacity=".6" stroke-width="4"/><rect x="90" y="68" width="20" height="112" fill="' + acc + '"/><path d="M100 68 C70 20 28 44 62 66 Z" fill="' + acc + '"/><path d="M100 68 C130 20 172 44 138 66 Z" fill="' + acc + '"/><circle cx="100" cy="68" r="9" fill="' + acc + '" stroke="' + ink + '" stroke-opacity=".7" stroke-width="3"/><path d="M170 30 l5 14 14 5 -14 5 -5 14 -5 -14 -14 -5 14 -5z" fill="' + ink + '" fill-opacity=".85"/><path d="M26 40 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3z" fill="' + acc + '"/><circle cx="188" cy="110" r="4" fill="' + ink + '" fill-opacity=".6"/><circle cx="14" cy="120" r="4" fill="' + acc + '"/></svg>' };
export const DEFAULT_DESIGN = { client_name: '', client_logo: '', color_1: '#12284C', color_2: '#1BA39C', accent: '#F2A93B',
  terms_ar: 'البطاقة لحاملها وتُستخدم كوسيلة دفع على المشتريات من المحل.\nلا تُستبدل بنقد. الرصيد المتبقي يبقى على البطاقة.\nالاحتفاظ بالبطاقة مسؤولية حاملها.',
  terms_en: 'Redeemable in store as a payment method. Not exchangeable for cash. Remaining balance stays on the card.' };
const design = (d) => { const o = { ...DEFAULT_DESIGN }; Object.entries(d || {}).forEach(([k, v]) => { if (v) o[k] = v; }); return o; };
const front = (c, d, cur, o) => {
  const plain = !!o.dataOnly; const logo = d.client_logo ? `<img class="glogo" src="${esc(d.client_logo)}">` : '';
  const top = plain ? '' : `<div class="gtop"><div class="gbrand gfixed" style="font-size:46px;gap:18px">${MARK.replace('width="70" height="70"', 'width="104" height="104"')}<b>ORBIT</b></div><div class="gclient">${logo}<span>${esc(d.client_name)}</span></div></div><div class="gkind">بطاقة هدية · GIFT CARD</div>${giftIcon(d.accent, 250, 'position:absolute;right:30px;top:112px;transform:rotate(8deg)')}`;
  const style = plain ? 'background:none;color:#000' : `background:linear-gradient(135deg,${d.color_1},${d.color_1}e6);color:#fff`;
  return `<div class="gcell${plain ? ' plain' : ''}"><div class="gcard" data-kind="front" style="${style}">${top}
<div class="gval" style="color:${plain ? '#000;padding-top:150px' : d.accent}">${esc(Number(c.value).toLocaleString('en-US'))}<small> ${esc(cur)}</small></div>
<div class="gmid"><div class="gqr">${qrSvg(c.card_no)}</div><div><div class="glab">${plain ? '' : 'رقم البطاقة · Card No.'}</div><div class="gno">${esc(c.card_no)}</div><div class="gbar">${barSvg(c.card_no)}</div></div></div>${plain ? '' : `<div class="gfoot">${esc(d.client_name)} · Orbit POS</div>`}</div></div>`;
};
const back = (d) => `<div class="gcell"><div class="gcard" data-kind="back" style="background:#F1F5F9;color:${d.color_1}"><div style="height:70px;background:${d.color_1};display:flex;align-items:center;justify-content:space-between;padding:0 30px;direction:ltr;color:#fff"><span class="gbrand gfixed" style="font-size:32px;gap:12px">${MARK.replace('width="70" height="70"', 'width="58" height="58"')}<b>ORBIT</b></span><span style="font-size:24px">${esc(d.client_name)}</span></div>
${giftIcon(d.color_2, 150, 'position:absolute;right:26px;bottom:60px;opacity:.6', d.color_1)}
<div style="direction:rtl;padding:26px 40px;font-size:19px;line-height:1.7"><b style="font-size:23px">الشروط · Terms</b><br>${String(d.terms_ar).split('\n').filter(Boolean).map((x) => '• ' + esc(x)).join('<br>')}<br><span dir="ltr" style="display:block;margin-top:6px">${esc(d.terms_en)}</span></div>
<div style="position:absolute;bottom:22px;left:40px;right:40px;font-size:17px;display:flex;justify-content:space-between"><span>${esc(d.client_name)}</span><span>توقيع / Signature: ____________</span></div></div></div>`;
// crop marks sit in the gaps between cards (A4 layout: 15.4 mm side margin, 31 mm top, 85.6 x 54 mm cards, 8 mm / 6 mm gaps)
function cropMarks(n) {
  const X0 = 15.4, Y0 = 31, W = 85.6, H = 54, GX = 8, GY = 6, off = 0.6, len = 2.2; let d = '';
  for (let i = 0; i < n; i++) { const x = X0 + (i % 2) * (W + GX), y = Y0 + Math.floor(i / 2) * (H + GY);
    [[x, y, -1, -1], [x + W, y, 1, -1], [x, y + H, -1, 1], [x + W, y + H, 1, 1]].forEach((c) => { d += `M${c[0] + c[2] * off} ${c[1]}h${c[2] * len}M${c[0]} ${c[1] + c[3] * off}v${c[3] * len}`; }); }
  return `<svg class="gcrop" viewBox="0 0 210 297" xmlns="http://www.w3.org/2000/svg"><path d="${d}" stroke="#000" stroke-width=".18" fill="none"/></svg>`;
}
export const SHEET_CSS = '*{box-sizing:border-box;margin:0}.pg{position:relative;width:210mm;height:297mm;padding:31mm 15.4mm 0;display:grid;grid-template-columns:85.6mm 85.6mm;grid-auto-rows:54mm;gap:6mm 8mm;page-break-after:always;direction:ltr;background:#fff}.pg.back{direction:rtl}.gcrop{position:absolute;left:0;top:0;width:210mm;height:297mm}' +
  '.gcell{width:85.6mm;height:54mm;overflow:hidden}.gcard{zoom:.378;width:856px;height:540px;position:relative;overflow:hidden;-webkit-print-color-adjust:exact;print-color-adjust:exact}' +
  '.gtop{display:flex;justify-content:space-between;padding:30px 44px 0;direction:ltr;align-items:center}.gbrand{display:flex;align-items:center;gap:14px;font-size:34px;letter-spacing:6px}.gclient{display:flex;align-items:center;gap:14px;font-size:30px;font-weight:700;max-width:430px;direction:rtl}.glogo{max-height:70px;max-width:150px;object-fit:contain;background:#fff;border-radius:8px;padding:4px}.gkind{padding:6px 44px 0;font-size:20px;letter-spacing:3px;opacity:.75;direction:ltr}' +
  '.gval{font-size:120px;font-weight:800;padding:14px 44px 0;direction:ltr;line-height:1}.gval small{font-size:28px;font-weight:400;opacity:.85}.gmid{position:absolute;left:44px;right:44px;bottom:70px;display:flex;gap:26px;align-items:flex-end;direction:ltr}.gqr{background:#fff;padding:8px;border-radius:12px;line-height:0}' +
  '.glab{font-size:17px;opacity:.75;margin-bottom:6px}.gno{font-size:34px;letter-spacing:4px;font-family:Consolas,"DejaVu Sans Mono",monospace;margin-bottom:10px}.gbar{background:#fff;padding:6px 10px;border-radius:8px;display:inline-block;line-height:0}.gfoot{position:absolute;bottom:20px;left:0;right:0;text-align:center;font-size:17px;opacity:.7}';
export function sheetBody(cards, dsn, cur, o = {}) {
  const d = design(dsn); const marks = o.cropMarks !== false; const pages = []; for (let i = 0; i < cards.length; i += 8) pages.push(cards.slice(i, i + 8));
  const crop = (n) => (marks ? cropMarks(n) : '');
  return pages.map((p) => `<div class="pg" data-page="front">${p.map((c) => front(c, d, cur, o)).join('')}${crop(p.length)}</div>`).join('') +
    (o.dataOnly ? '' : `<div class="pg back" data-page="back">${Array(Math.min(8, cards.length)).fill(back(d)).join('')}${crop(Math.min(8, cards.length))}</div>`);
}
export function sheetHtml(cards, dsn, cur, o = {}) {
  return `<!doctype html><html><head><meta charset="utf-8"><title>Gift cards</title><style>@page{size:A4;margin:0}body{font-family:"Segoe UI","Noto Sans Arabic",Tahoma,Arial,sans-serif}${SHEET_CSS}</style></head><body>${sheetBody(cards, dsn, cur, o)}</body></html>`;
}
// opens the sheet in a new tab and the print dialog (choose "Save as PDF" there to get a PDF file)
export function printSheet(cards, dsn, cur, o = {}) {
  const w = window.open('', '_blank'); if (!w) return false;
  w.document.write(sheetHtml(cards, dsn, cur, o)); w.document.close(); setTimeout(() => w.print(), 400); return true;
}
