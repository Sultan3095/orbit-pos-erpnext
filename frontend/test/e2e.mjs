import puppeteer from 'puppeteer-core';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
const OUT = process.env.OUT || '/tmp/erp-shots'; fs.mkdirSync(OUT, { recursive: true });
const srv = spawn('npx', ['vite', 'preview', '--port', '4173', '--outDir', '../orbit_pos/public/pos'], { stdio: 'ignore' });
await new Promise((r) => setTimeout(r, 2500));
const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'], headless: 'new' });
try {
  const p = await b.newPage(); await p.setViewport({ width: 1200, height: 760 });
  const txt = (sel) => p.$eval(sel, (e) => e.textContent);
  await p.goto('http://localhost:4173/?mock=1'); await p.waitForSelector('[data-testid=noshift]');
  assert.equal(await p.evaluate(() => document.documentElement.dir), 'rtl');
  await p.screenshot({ path: OUT + '/1-noshift-ar.png' });
  await p.click('[data-testid=open]'); await p.waitForSelector('[data-testid=scan]');
  for (const c of ['5*6221', '6222']) { await p.type('[data-testid=scan]', c); await p.keyboard.press('Enter'); await new Promise((r) => setTimeout(r, 300)); }
  await p.waitForFunction(() => document.querySelector('[data-testid=total]').textContent.includes('20.00'));
  // 5 chips (4.00) with buy2get3 -> 8.00, juice 12 -> 20.00 total
  assert.ok((await txt('[data-testid=total]')).includes('20.00'), await txt('[data-testid=total]'));
  await p.screenshot({ path: OUT + '/2-cart-promo-ar.png' });
  await p.type('[data-testid=cash]', '10'); await p.type('[data-testid=card]', '10');
  assert.equal(await p.$eval('[data-testid=pay]', (e) => e.disabled), false);
  await p.select('[data-testid=lang]', 'en'); await p.select('[data-testid=theme]', 'blue');
  assert.equal(await p.evaluate(() => document.documentElement.dir), 'ltr');
  await p.screenshot({ path: OUT + '/3-blue-en.png' });
  await p.click('[data-testid=pay]'); await new Promise((r) => setTimeout(r, 600));
  assert.ok((await txt('[data-testid=msg]')).includes('Sale complete'));
  assert.equal((await txt('[data-testid=pending]')).trim().endsWith('0'), true, await txt('[data-testid=pending]'));
  // unknown item
  await p.type('[data-testid=scan]', '999'); await p.keyboard.press('Enter'); await new Promise((r) => setTimeout(r, 300));
  assert.ok((await txt('[data-testid=msg]')).includes('Item not found'));
  await p.select('[data-testid=theme]', 'dark'); await p.screenshot({ path: OUT + '/4-dark.png' });
  // petty cash: reason is mandatory, small cash-out saves, large one asks for the manager PIN
  await p.click('[data-testid=cash-out]'); await p.waitForSelector('[data-testid=cm-dialog]');
  await p.type('[data-testid=cm-amount]', '50'); await p.click('[data-testid=cm-save]');
  assert.ok((await txt('[data-testid=cm-err]')).includes('required'), 'reason required');
  await p.type('[data-testid=cm-reason]', 'bags from the supermarket'); await p.screenshot({ path: OUT + '/5-cashout-dialog.png' });
  await p.click('[data-testid=cm-save]'); await new Promise((r) => setTimeout(r, 400));
  assert.equal(await p.$('[data-testid=cm-dialog]'), null); assert.ok((await txt('[data-testid=msg]')).includes('50.00'));
  await p.click('[data-testid=cash-out]'); await p.type('[data-testid=cm-amount]', '300'); await p.type('[data-testid=cm-reason]', 'big');
  await p.click('[data-testid=cm-save]'); await p.waitForSelector('[data-testid=cm-pin]'); await p.screenshot({ path: OUT + '/6-cashout-pin.png' });
  await p.click('[data-testid=cash-in]'); // reopen as cash in resets the dialog
  await p.type('[data-testid=cm-amount]', '5'); await p.type('[data-testid=cm-reason]', 'float'); await p.click('[data-testid=cm-save]'); await new Promise((r) => setTimeout(r, 400));
  assert.equal(await p.$('[data-testid=cm-dialog]'), null);
  await p.type('[data-testid=counted]', '0'); await p.click('[data-testid=close]'); await p.waitForSelector('[data-testid=z]');
  console.log('UI e2e (mock API) PASSED');
} finally { await b.close(); srv.kill(); }
