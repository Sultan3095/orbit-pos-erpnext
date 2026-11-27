import puppeteer from 'puppeteer-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
// Full-flow captures for the web manuals in one language. Run: OUT=/tmp/dir LANG=en|ar node test/capture_flows.mjs
const OUT = process.env.OUT || '/tmp/web-flow-shots'; fs.mkdirSync(OUT, { recursive: true });
const LANG = process.env.LANG || 'en';
const srv = spawn('npx', ['vite', 'preview', '--port', '4175', '--outDir', '../orbit_pos/public/pos'], { stdio: 'ignore' });
await new Promise((r) => setTimeout(r, 2500));
const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'], headless: 'new' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const el = async (p, sel, name) => { const e = await p.$(sel); if (e) await e.screenshot({ path: `${OUT}/${name}.png` }); else console.error('MISSING', sel, name); };
const dom = (p, sel) => p.evaluate((s) => { const t = document.querySelector(s); if (t) t.click(); }, sel);
try {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 900 });
  await p.evaluateOnNewDocument((lang) => { try { localStorage.setItem('orbit_lang', lang); } catch (e) {} }, LANG);
  await p.goto('http://localhost:4175/?mock=1'); await p.waitForSelector('[data-testid=noshift]'); await sleep(700);
  // 1. no-shift / open / promos / customer / cart
  await el(p, '[data-testid=noshift]', `03-pos-no-shift`);
  await p.click('[data-testid=open]'); await p.waitForSelector('[data-testid=scan]'); await sleep(400);
  await p.screenshot({ path: `${OUT}/05-pos-active-promos.png` });
  await el(p, '[data-testid=customer-picker]', `06-pos-customer`).catch(() => {});
  // cart with promo
  for (const c of ['5*6221', '6222']) { await p.type('[data-testid=scan]', c); await p.keyboard.press('Enter'); await sleep(300); }
  await p.waitForFunction(() => document.querySelector('[data-testid=total]').textContent.includes('20.00'));
  await p.screenshot({ path: `${OUT}/08-pos-cart-promo.png` });
  // payment panel with cash+card typed
  await p.type('[data-testid=cash]', '10'); await p.type('[data-testid=card]', '10');
  await el(p, 'aside.pay', `09-pos-payment`);
  // receipt after pay
  await dom(p, '[data-testid=pay]'); await sleep(800);
  await el(p, '[data-testid=receipt-modal]', `10-pos-receipt-sale`);
  await dom(p, '[data-testid=receipt-close]'); await sleep(300);
  // 2. returns flow
  await dom(p, '[data-testid=tab-returns]'); await p.waitForSelector('[data-testid=ret-search]'); await sleep(300);
  await p.type('[data-testid=ret-search]', 'SINV'); await dom(p, '[data-testid=ret-find]');
  await p.waitForSelector('[data-testid=inv-row]'); await sleep(200);
  await p.screenshot({ path: `${OUT}/14-ret-search.png` });
  await dom(p, '[data-testid=inv-row]'); await p.waitForSelector('[data-testid=ret-invoice]'); await sleep(300);
  await p.screenshot({ path: `${OUT}/16-ret-invoice.png` });
  // promo line: select 1 chips -> exchange-only note visible; confirm -> exchange receipt
  const qtyInputs = await p.$$('[data-testid=ret-invoice] input[type=number], [data-testid=ret-invoice] input');
  // set qty on first line via its input
  await p.evaluate(() => { const inp = document.querySelector('[data-testid=ret-line] input'); if (inp) { Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(inp, '1'); inp.dispatchEvent(new Event('input', { bubbles: true })); } });
  await sleep(300);
  await p.screenshot({ path: `${OUT}/17-ret-promo-exchange-only.png` });
  await dom(p, '[data-testid=ret-confirm]'); await sleep(800);
  await dom(p, '[data-testid=receipt-close]'); await sleep(200);
  await el(p, '[data-testid=ret-done]', `18-ret-exchange-receipt`);
  // use the receipt now -> sell view with credit applied
  await dom(p, '[data-testid=ret-use-now]'); await sleep(600);
  await p.evaluate(() => { const g = document.querySelector('#guide [data-g=x]'); if (g) g.click(); }); await sleep(200);
  await el(p, '[data-testid=xr-box]', `18b-xr-applied`).catch(() => {});
  for (const c of ['6221']) { await p.type('[data-testid=scan]', c); await p.keyboard.press('Enter'); await sleep(300); }
  await p.screenshot({ path: `${OUT}/20-exchange-cart.png` });
  await p.evaluate(() => { localStorage.removeItem('orbit_xr'); });
  // 2b. pay with coupon + gift card applied
  await p.evaluate(() => { const b = [...document.querySelectorAll('[data-testid=line] button')].pop(); });
  for (const c of ['6222']) { await p.type('[data-testid=scan]', c); await p.keyboard.press('Enter'); await sleep(300); }
  await p.type('[data-testid=coupon-code]', 'WELCOME10'); await dom(p, '[data-testid=coupon-apply]'); await sleep(300);
  await p.type('[data-testid=gift-no]', 'GC-1001'); await dom(p, '[data-testid=gift-apply]'); await sleep(300);
  await el(p, 'aside.pay', `34-web-pay-coupon-gift`);
  await p.evaluate(() => { const rm = [...document.querySelectorAll('[data-testid=coupon-applied] button, [data-testid=gift-applied] button')]; rm.forEach((x) => x.click()); }); await sleep(200);
  await p.evaluate(() => { const b = [...document.querySelectorAll('[data-testid=line] button')].pop(); if (b) b.click(); }); await sleep(200);
  // 3. serials: sell a serial item (clear cart + credit first)
  await p.evaluate(() => { const xr = document.querySelector('[data-testid=xr-applied] button'); if (xr) xr.click(); });
  await sleep(200);
  await p.evaluate(() => { [...document.querySelectorAll('[data-testid=line] button')].forEach((x) => x.click()); }); await sleep(200);
  await p.type('[data-testid=scan]', '7001'); await p.keyboard.press('Enter'); await sleep(300);
  await p.type('[data-testid=serial-input]', 'SN-100'); await sleep(200);
  await p.screenshot({ path: `${OUT}/22-serial-sale.png` });
  // 4. coupons tab
  await dom(p, '[data-testid=tab-coupons]'); await p.waitForSelector('[data-testid=coupons]'); await sleep(400);
  await p.screenshot({ path: `${OUT}/31-web-coupons-list.png` });
  await dom(p, '[data-testid=cp-add]'); await p.waitForSelector('[data-testid=cp-form]'); await sleep(200);
  await p.type('[data-testid=cf-code]', 'RAMADAN15');
  await el(p, '[data-testid=cp-form]', `30-web-coupon-form`);
  // 5. gifts tab
  await dom(p, '[data-testid=tab-gifts]'); await p.waitForSelector('[data-testid=gifts]'); await sleep(500);
  await p.screenshot({ path: `${OUT}/37-web-gift-by-value.png` });
  await dom(p, '[data-testid=gift-sell-open]'); await p.waitForSelector('[data-testid=gift-form]');
  await p.type('[data-testid=gf-amount]', '500');
  await el(p, '[data-testid=gift-form]', `32-web-gift-sell-form`);
  await dom(p, '[data-testid=gf-save]'); await p.waitForSelector('[data-testid=gift-sold]'); await sleep(300);
  await el(p, '[data-testid=gift-sold]', `33-web-gift-sold`);
  await dom(p, '[data-testid=gh-GC-1001]'); await p.waitForSelector('[data-testid=gift-history]'); await sleep(200);
  await el(p, '[data-testid=gift-history]', `36-web-gift-history`);
  await dom(p, '[data-testid=gw-GC-1002]'); await p.waitForSelector('[data-testid=gift-wo-form]'); await sleep(200);
  await el(p, '[data-testid=gift-wo-form]', `38-web-gift-writeoff-form`);
  await dom(p, '[data-testid=gift-print-open]'); await p.waitForSelector('[data-testid=gift-print-form]');
  await p.type('[data-testid=gp-value]', '100');
  await el(p, '[data-testid=gift-print-form]', `40-web-gift-print-form`);
  await dom(p, '[data-testid=gp-go]'); await p.waitForSelector('[data-testid=gift-sheet]'); await sleep(500);
  await p.screenshot({ path: `${OUT}/41-web-gift-cards-sheet.png` });
  // 6. edit invoice
  await dom(p, '[data-testid=tab-edit]'); await p.waitForSelector('[data-testid=edit-screen]'); await sleep(300);
  await p.type('[data-testid=ed-q]', 'SINV'); await dom(p, '[data-testid=ed-search]'); await sleep(400);
  await dom(p, '[data-testid=ed-pick-SINV-1]'); await p.waitForSelector('[data-testid=ed-closed]'); await sleep(200);
  await el(p, '[data-testid=ed-closed]', `49-web-edit-closed`);
  await dom(p, '[data-testid=tab-edit]'); await sleep(200);
  await p.type('[data-testid=ed-q]', 'SINV'); await dom(p, '[data-testid=ed-search]'); await sleep(400);
  await dom(p, '[data-testid=ed-pick-SINV-2]'); await p.waitForSelector('[data-testid=ed-form]'); await sleep(300);
  await p.screenshot({ path: `${OUT}/50-web-edit-form.png` });
  console.log('CAPTURE OK', OUT);
} finally { await b.close(); srv.kill(); }
