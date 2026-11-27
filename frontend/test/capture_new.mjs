import puppeteer from 'puppeteer-core';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
// Captures the NEW-feature web screens (provider tender, ETA, approvals + second manager, recounts)
// against the built-in ?mock=1 API. Run: OUT=/tmp/dir LANG=ar|en node test/capture_new.mjs
const OUT = process.env.OUT || '/tmp/web-new-shots'; fs.mkdirSync(OUT, { recursive: true });
const LANG = process.env.LANG || 'ar';
const srv = spawn('npx', ['vite', 'preview', '--port', '4174', '--outDir', '../orbit_pos/public/pos'], { stdio: 'ignore' });
await new Promise((r) => setTimeout(r, 2500));
const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--font-render-hinting=none'], headless: 'new' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shotEl = async (p, sel, name) => { const el = await p.$(sel); if (el) await el.screenshot({ path: `${OUT}/${name}.png` }); else console.error('MISSING', sel, name); };
try {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 860 });
  await p.evaluateOnNewDocument((lang) => { try { localStorage.setItem('orbit_lang', lang); } catch (e) {} }, LANG);
  await p.goto('http://localhost:4174/?mock=1'); await p.waitForSelector('[data-testid=noshift]'); await sleep(600);
  // 1. manager approvals on the no-shift screen: pending close + review with second-manager fields
  await p.waitForSelector('[data-testid=pc-SHIFT-00042]');
  await shotEl(p, '[data-testid=approvals]', `approvals-list-${LANG}`);
  await p.click('[data-testid=pc-SHIFT-00042]'); await p.waitForSelector('[data-testid=close-view]'); await sleep(300);
  await shotEl(p, '[data-testid=close-view]', `approvals-view-second-${LANG}`);
  // 2. open shift, sell, provider tender
  await p.click('[data-testid=open]'); await p.waitForSelector('[data-testid=scan]');
  for (const c of ['5*6221', '6222']) { await p.type('[data-testid=scan]', c); await p.keyboard.press('Enter'); await sleep(300); }
  await p.waitForFunction(() => document.querySelector('[data-testid=total]').textContent.includes('20.00'));
  await p.waitForSelector('[data-testid=prov-paymob]'); await sleep(200);
  await p.screenshot({ path: `${OUT}/sell-providers-${LANG}.png` });
  await p.click('[data-testid=prov-paymob]'); await p.waitForSelector('[data-testid=prov-attempt]'); await sleep(200);
  await shotEl(p, '[data-testid=prov-box]', `provider-paymob-pending-${LANG}`);
  await p.click('[data-testid=prov-mock-paid]'); await sleep(400);
  await shotEl(p, '[data-testid=prov-box]', `provider-paid-${LANG}`);
  await p.click('[data-testid=prov-remove]'); await sleep(200);
  await p.click('[data-testid=prov-fawry]'); await p.waitForSelector('[data-testid=prov-attempt]'); await sleep(200);
  await shotEl(p, '[data-testid=prov-box]', `provider-fawry-pending-${LANG}`);
  await p.click('[data-testid=prov-remove]'); await sleep(200);
  // 3. pay cash in full, then ETA tab
  await p.type('[data-testid=cash]', '20'); await p.click('[data-testid=pay]'); await sleep(700);
  await p.screenshot({ path: `${OUT}/after-pay-${LANG}.png` });
  await p.evaluate(() => { const c = document.querySelector('[data-testid=receipt-close]'); if (c) c.click(); }); await sleep(300);
  await p.evaluate(() => { const t = document.querySelector('[data-testid=tab-eta]'); if (t) t.click(); });
  await p.waitForSelector('[data-testid=eta]'); await sleep(400);
  await shotEl(p, '[data-testid=eta]', `eta-${LANG}`);
  // 4. cashier persona: recount sent back by the manager
  const p2 = await b.newPage(); await p2.setViewport({ width: 1280, height: 860 });
  await p2.evaluateOnNewDocument((lang) => { try { localStorage.setItem('orbit_lang', lang); } catch (e) {} }, LANG);
  await p2.goto('http://localhost:4174/?mock=1&persona=cashier'); await p2.waitForSelector('[data-testid=recounts]'); await sleep(400);
  await shotEl(p2, '[data-testid=recounts]', `recounts-cashier-${LANG}`);
  console.log('CAPTURE OK', OUT);
} finally { await b.close(); srv.kill(); }
