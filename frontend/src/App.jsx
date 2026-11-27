import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { t } from './i18n.js';
import { api } from './api.js';
import { createQueue, newTxnId } from './queue.js';
import Receipt from './Receipt.jsx';
import Returns from './Returns.jsx';
import Approvals from './Approvals.jsx';
import Eta from './Eta.jsx';
import { applyPromotions, r2 as pr2 } from './promosLocal.js';
import EditInvoice from './EditInvoice.jsx';
import Gifts, { GiftShiftBlock } from './Gifts.jsx';
import Coupons from './Coupons.jsx';
import { showGuide, closeGuide, guideOff, setGuideOff, fail, ctx } from './guide.js';

const queue = createQueue(window.localStorage);
const TERMINAL = localStorage.getItem('orbit_terminal') || (localStorage.setItem('orbit_terminal', 'T' + Math.random().toString(36).slice(2, 6)), localStorage.getItem('orbit_terminal'));
const lastResult = {};   // txn_id -> server answer of the sale, used to print its receipt
const THEMES = ['brand', 'galaxy', 'light', 'dark'];
const normTheme = (v) => (v === 'blue' ? 'brand' : THEMES.includes(v) ? v : 'brand');   // the old blue theme is the brand theme now
const fmt = (n) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);

export default function App() {
  const [lang, setLang] = useState(localStorage.getItem('orbit_lang') || 'ar');
  const [theme, setTheme] = useState(normTheme(localStorage.getItem('orbit_theme')));
  const [me, setMe] = useState('');
  const [shift, setShift] = useState(null);
  const [perms, setPerms] = useState({});
  const [cart, setCart] = useState([]);
  const [quote, setQuote] = useState(null);
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState('');
  const [cashPaid, setCashPaid] = useState('');
  const [cardPaid, setCardPaid] = useState('');
  const [cardRef, setCardRef] = useState('');
  const [opening, setOpening] = useState('0');
  const [counted, setCounted] = useState('');
  const [z, setZ] = useState(null);
  const [cm, setCm] = useState(null);   // cash in/out dialog state
  const [online, setOnline] = useState(true);
  const [view, setView] = useState('sale');
  const [customer, setCustomer] = useState(null);          // null = cash customer
  const [custQ, setCustQ] = useState('');
  const [custList, setCustList] = useState([]);
  const [newCust, setNewCust] = useState(null);
  const [promos, setPromos] = useState([]);
  const promosRef = useRef([]);
  const [rc, setRc] = useState(null);                      // receipt being shown / printed
  const [xr, setXr] = useState(null);                      // exchange receipt applied to this sale
  const [xrCode, setXrCode] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [couponIn, setCouponIn] = useState('');
  const [giftNo, setGiftNo] = useState('');
  const [giftAmt, setGiftAmt] = useState('');
  const [gift, setGift] = useState(null);                  // checked gift card applied to this sale
  const [payCfg, setPayCfg] = useState({ mode: 'off', providers: [] });
  const [prov, setProv] = useState(null);                  // open provider payment attempt (Paymob / Fawry)
  const [provTxn, setProvTxn] = useState('');              // txn id reserved for that attempt
  const [pending, setPending] = useState(queue.list().length);
  const [failed, setFailed] = useState(queue.failed());
  const counter = useRef(Number(localStorage.getItem('orbit_counter') || 0));
  const L = (k) => t(lang, k);
  const [gOff, setGOff] = useState(false);
  useEffect(() => { setGOff(guideOff(me)); }, [me]);
  ctx.lang = lang; ctx.user = me;
  const hint = (key, force) => showGuide(key, { lang, user: me, force });

  useEffect(() => {
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = lang; document.documentElement.dataset.theme = theme;
    localStorage.setItem('orbit_lang', lang); localStorage.setItem('orbit_theme', theme);
    if (me) localStorage.setItem('orbit_theme:' + me, theme);
  }, [lang, theme, me]);

  useEffect(() => { api('payments.config').then(setPayCfg).catch(() => {}); api('shift.my_permissions').then((r) => { setPerms(r.perms || {}); if (r.user) { setMe(r.user); setTheme(normTheme(r.theme || localStorage.getItem('orbit_theme:' + r.user) || localStorage.getItem('orbit_theme'))); } }).catch(() => setPerms({})); }, []);
  const refreshShift = useCallback(async () => { try { setShift(await api('shift.current_shift')); setOnline(true); } catch (e) { setOnline(false); } }, []);
  useEffect(() => { refreshShift(); }, [refreshShift]);
  useEffect(() => { if (shift) api('exchange.active_promotions').then((r) => { setPromos(r); promosRef.current = r; localStorage.setItem('orbit_promos', JSON.stringify(r)); }).catch(() => { const c = JSON.parse(localStorage.getItem('orbit_promos') || '[]'); setPromos(c); promosRef.current = c; }); }, [shift]);
  useEffect(() => {
    if (custQ.trim().length < 2) { setCustList([]); return; }
    let live = true;
    api('exchange.search_customers', { q: custQ.trim() }).then((r) => { if (live) setCustList(r); }).catch(() => {});
    return () => { live = false; };
  }, [custQ]);

  const flush = useCallback(async () => {
    try {
      await queue.flush(async (p) => { const r = await api('sales.submit_sale', { payload: JSON.stringify(p) }); lastResult[p.txn_id] = r; return r; });
      setOnline(true);
    } catch (e) { setOnline(false); }
    setPending(queue.list().length);
    const f = queue.failed(); setFailed((old) => { if (f.length > old.length) setTimeout(() => showGuide('REJECTED', { lang: ctx.lang, user: ctx.user, force: true }), 50); return f; });
  }, []);
  useEffect(() => { const id = setInterval(flush, 15000); window.addEventListener('online', flush); return () => { clearInterval(id); window.removeEventListener('online', flush); }; }, [flush]);

  // The server prices the cart (promotions, discounts). The client only displays the result.
  useEffect(() => {
    if (!cart.length) { setQuote(null); return; }
    let live = true;
    api('sales.quote', { payload: JSON.stringify({ lines: cart.map(({ itemId, group, qty, price }) => ({ itemId, group, qty, price })), coupon: couponCode || undefined, customer: customer ? customer.name : undefined, shift: shift ? shift.name : undefined }) })
      .then((q) => { if (live) setQuote(q); }).catch((err) => {
        if (!live) return;
        if (couponCode && err.permanent) { setMsg(fail(err)); setCouponCode(''); hint('COUPON'); return; }   // a coupon the server refuses is dropped, with the reason
        setQuote(localQuote(cart, promosRef.current));
      });
    return () => { live = false; };
  }, [cart, couponCode, customer]);

  const serialList = (l) => (l.serials || '').split(/[\s,;]+/).filter(Boolean);
  const total = quote ? quote.net_before_tax : 0;
  const credit = xr ? Math.min(xr.amount, total) : 0;
  const giftCover = gift ? Math.max(0, Math.min(gift.balance, total - credit, Number(giftAmt) > 0 ? Number(giftAmt) : Infinity)) : 0;
  const serialsOk = cart.every((l) => !l.hasSerial || serialList(l).length === l.qty);
  useEffect(() => {
    const ch = new BroadcastChannel('orbit-display');
    ch.postMessage({ lang, theme, total, lines: (quote ? quote.lines : []).map((l, i) => ({ name: cart[i] ? cart[i].name : '', qty: l.qty, price: l.price, net: l.net })) });
    ch.close();
  }, [quote, lang, theme, cart, total]);

  async function add(e) {
    e.preventDefault(); setMsg('');
    let c = code.trim(), qty = 1;
    const m = c.match(/^(\d+(?:\.\d+)?)\*(.+)$/); if (m) { qty = Number(m[1]); c = m[2]; }
    if (!c) return;
    if (/^EXR-/i.test(c)) { setCode(''); return applyReceipt(c.toUpperCase()); }
    try {
      const it = await api('sales.lookup', { code: c });
      setCart((cur) => {
        const i = cur.findIndex((x) => x.itemId === it.name && !it.orbit_weighed);
        const q = qty * (it.qty || 1);
        if (i >= 0 && !it.has_serial_no) return cur.map((x, k) => (k === i ? { ...x, qty: x.qty + q } : x));
        return [...cur, { itemId: it.name, name: it.item_name, group: it.item_group, price: it.price, qty: q, hasSerial: !!it.has_serial_no, serials: '' }];
      });
      setCode('');
    } catch (err) { setMsg(L('notFound') + ': ' + c); hint('NOT_FOUND'); }
  }

  const provPaid = prov && prov.state === 'paid' ? Number(prov.amount) || 0 : 0;
  const paid = (Number(cashPaid) || 0) + (Number(cardPaid) || 0) + credit + giftCover + provPaid;
  const remaining = Math.max(0, total - paid);
  const change = Math.max(0, paid - total);
  // offline the screen has no server prices: when an offer or coupon could change the total, selling would charge
  // the wrong amount, so Pay waits for the connection
  // offline the screen prices offers itself (same rules as the server). Only a coupon still waits for the
  // connection, because its validity and usage limits live on the server. A promo list cached before the
  // offline engine existed (no .engine) also waits: its totals could be wrong.
  const promosLegacy = (promosRef.current || []).some((p) => !p.engine);
  const offlineBlock = !!(quote && quote.local && (couponCode || promosLegacy));
  const canPay = cart.length && quote && paid + 0.005 >= total && shift && serialsOk && !offlineBlock;
  useEffect(() => { if (prov && prov.state !== 'paid') { setProv(null); setProvTxn(''); } }, [cart]);
  async function startProv(provider) {
    setMsg('');
    const amount = remaining;
    if (!(amount > 0)) { hint('EMPTY_CART'); return; }
    const txn = provTxn || newTxnId(TERMINAL, counter.current + 1);
    try {
      const r = await api('payments.create_payment', { provider, payload: JSON.stringify({ txn_id: txn, shift: shift.name, amount, currency: 'EGP', lines: cart.map(({ itemId, group, qty, price }) => ({ itemId, group, qty, price })), ...(customer ? { customer: customer.name } : {}) }) });
      setProvTxn(txn); setProv(r);
    } catch (e) { setMsg(fail(e)); }
  }
  async function checkProv() { try { setProv(await api('payments.payment_status', { name: prov.name })); } catch (e) { setMsg(fail(e)); } }
  async function settleProv() { try { setProv(await api('payments.mock_settle', { name: prov.name, state: 'paid' })); } catch (e) { setMsg(fail(e)); } }

  async function applyReceipt(name) {
    setMsg('');
    try {
      const info = await api('exchange.exchange_receipt_info', { name });
      if (info.status !== 'Open') { setMsg(`${name}: ${info.status}`); return; }
      setXr(info); setXrCode('');
    } catch (err) { setMsg(fail(err)); }
  }
  async function applyCoupon() {
    setMsg('');
    if (!couponIn.trim()) return;
    try { await api('sales.quote', { payload: JSON.stringify({ lines: cart.map(({ itemId, group, qty, price }) => ({ itemId, group, qty, price })), coupon: couponIn.trim(), customer: customer ? customer.name : undefined, shift: shift.name }) }); setCouponCode(couponIn.trim().toUpperCase()); setCouponIn(''); setMsg(L('cpApplied')); }
    catch (err) { setMsg(fail(err)); hint('COUPON'); }
  }
  async function applyGift() {
    setMsg('');
    try { const g = await api('gifts.check_gift_card', { card_no: giftNo }); if (g.status !== 'active') { setMsg(giftNo + ': ' + L('giftState_' + g.status)); hint('GIFT'); return; } setGift(g); }
    catch (err) { setMsg(fail(err)); hint('GIFT'); }
  }
  async function newCustomer() {
    try { const c = await api('exchange.create_customer', { customer_name: newCust.name, mobile_no: newCust.phone }); setCustomer(c); setNewCust(null); setCustQ(''); setCustList([]); }
    catch (err) { setMsg(fail(err)); }
  }

  async function pay() {
    counter.current += 1; localStorage.setItem('orbit_counter', String(counter.current));
    const cash = Number(cashPaid) || 0, card = Number(cardPaid) || 0;
    const payments = [];
    if (cash) payments.push({ method: 'Cash', amount: cash });
    if (card) payments.push({ method: 'Credit Card', amount: card, ref: cardRef });
    if (prov && prov.state === 'paid') payments.push({ method: prov.provider === 'paymob' ? 'Paymob' : 'Fawry', amount: Number(prov.amount), attempt: prov.name });
    const payload = { txn_id: provTxn || newTxnId(TERMINAL, counter.current), terminal: TERMINAL, shift: shift.name,
      lines: cart.map((l) => ({ itemId: l.itemId, group: l.group, qty: l.qty, price: l.price, ...(l.hasSerial ? { serial_no: serialList(l) } : {}) })), payments };
    if (customer) payload.customer = customer.name;
    if (xr) payload.exchange_receipt = xr.name;
    if (couponCode) payload.coupon = couponCode;
    if (gift && giftCover > 0) { payload.gift_card = gift.card_no; if (Number(giftAmt) > 0) payload.gift_amount = Number(giftAmt); }
    queue.push(payload); setPending(queue.list().length);       // always queue first, so nothing is lost
    setCart([]); setCashPaid(''); setCardPaid(''); setCardRef(''); setXr(null); setCustomer(null); setCouponCode(''); setGift(null); setGiftNo(''); setGiftAmt(''); setProv(null); setProvTxn(''); setMsg(L('done') + (change ? ` — ${L('change')}: ${fmt(change)}` : ''));
    await flush();
    const res = lastResult[payload.txn_id];
    if (res && res.sales_invoice) { try { setRc(await api('exchange.get_receipt', { invoice: res.sales_invoice })); } catch (e) {} }
  }

  async function openShift() { try { setShift(await api('shift.open_shift', { pos_profile: localStorage.getItem('orbit_profile') || 'POS', opening_cash: opening, terminal: TERMINAL })); } catch (e) { setMsg(fail(e)); } }
  async function saveCashMove() {
    const amount = Number(cm.amount);
    if (!(amount > 0)) { setCm({ ...cm, err: L('invalidAmount') }); return; }
    if (cm.reason.trim().length < 3) { setCm({ ...cm, err: L('reasonRequired') }); hint('REASON'); return; }
    try {
      const args = { shift: shift.name, direction: cm.direction, amount, reason: cm.reason.trim() };
      if (cm.needPin) { args.manager = cm.manager; args.pin = cm.pin; }
      await api('shift.cash_movement', args);
      setMsg((cm.direction === 'Out' ? L('cashOut') : L('cashIn')) + ': ' + fmt(amount) + ' — ' + cm.reason.trim()); setCm(null);
    } catch (e) {
      const needs = /approval required|manager|PIN/i.test(e.message || '');
      setCm({ ...cm, needPin: cm.needPin || needs, err: fail(e) });
    }
  }
  async function closeShift() { if (String(counted).trim() === '' || !(Number(counted) >= 0)) { hint('COUNTED'); return; } try { const r = await api('shift.close_shift', { shift: shift.name, counted_cash: counted }); if (r.pending) { setZ(null); setMsg(L('closePending')); } else setZ(r); setShift(null); } catch (e) { setMsg(fail(e)); } }

  return (
    <div className="app">
      <header>
        <b>{L('app')}</b>
        <span className={'pill ' + (online ? 'ok' : 'bad')} data-testid="net">{online ? L('online') : L('offline')}</span>
        <span className="pill" data-testid="pending">{L('queued')}: {pending}</span>
        {failed.length > 0 && <span className="pill bad" data-testid="rejected-pill">{L('rejectedSales')}: {failed.length}</span>}
        <button onClick={flush}>{L('sync')}</button>
        <span className="tabs">
          <button className={view === 'sale' ? 'on' : ''} onClick={() => setView('sale')} data-testid="tab-sale">{L('tabSale')}</button>
          <button className={view === 'returns' ? 'on' : ''} onClick={() => setView('returns')} data-testid="tab-returns">{L('tabReturns')}</button>
          {(perms.editInvoice === 'Y' || perms.voidInvoice === 'Y' || perms.editInvoice === 'A') && <button className={view === 'edit' ? 'on' : ''} onClick={() => setView('edit')} data-testid="tab-edit">{L('tabEdit')}</button>}
          {perms.sellGiftCard === 'Y' && <button className={view === 'gifts' ? 'on' : ''} onClick={() => setView('gifts')} data-testid="tab-gifts">{L('tabGifts')}</button>}
          {perms.coupons === 'Y' && <button className={view === 'coupons' ? 'on' : ''} onClick={() => setView('coupons')} data-testid="tab-coupons">{L('tabCoupons')}</button>}
          {perms.viewOtherShifts === 'Y' && <button className={view === 'eta' ? 'on' : ''} onClick={() => setView('eta')} data-testid="tab-eta">{L('tabEta')}</button>}
          {perms.approve === 'Y' && perms.seeExpected === 'Y' && <button className={view === 'approvals' ? 'on' : ''} onClick={() => setView('approvals')} data-testid="tab-approvals">{L('tabApprovals')}</button>}
        </span>
        <span className="sp" />
        <label>{L('theme')} <select value={theme} onChange={(e) => { setTheme(e.target.value); api('shift.set_theme', { theme: e.target.value }).catch(() => {}); }} data-testid="theme">
          {THEMES.map((x) => <option key={x} value={x}>{L(x)}</option>)}</select></label>
        <label>{L('lang')} <select value={lang} onChange={(e) => setLang(e.target.value)} data-testid="lang"><option value="ar">العربية</option><option value="en">English</option></select></label>
        <a href="#display" target="_blank" rel="noreferrer">{L('customerScreen')}</a>
      </header>
      {failed.length > 0 && (
        <div className="msg" data-testid="rejected" role="alert">
          <b>{L('rejectedTitle')}</b>
          {failed.map((f) => (
            <div key={f.payload.txn_id} data-testid="rejected-row">
              <span dir="ltr">{f.payload.txn_id}</span> — {f.reason || L('rejectedNoReason')}{' '}
              <button onClick={() => { queue.retry(f.payload.txn_id); setFailed(queue.failed()); setPending(queue.list().length); flush(); }} data-testid="rejected-retry">{L('retry')}</button>{' '}
              <button onClick={() => { queue.dismiss(f.payload.txn_id); setFailed(queue.failed()); }} data-testid="rejected-dismiss">{L('dismiss')}</button>
            </div>))}
        </div>)}

      {!shift ? (
        <section className="card" data-testid="noshift">
          <h2>{L('noShift')}</h2>
          <label>{L('openingCash')} <input value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" /></label>
          <button className="primary" onClick={openShift} data-testid="open">{L('openShift')}</button>
          {z && <pre data-testid="z">{L('expected')}: {fmt(z.expected_cash)} / {L('countedCash')}: {fmt(z.counted_cash)} / {L('difference')}: {fmt(z.difference)}</pre>}
          {msg && <div className="msg" data-testid="close-pending-msg">{msg}</div>}
          <Recounts L={L} fmt={fmt} />
          {perms.approve === 'Y' && perms.seeExpected === 'Y' && <Approvals L={L} fmt={fmt} />}
          {(perms.editInvoice === 'Y' || perms.voidInvoice === 'Y') && <EditInvoice L={L} fmt={fmt} perms={perms} onReceipt={setRc} hint={hint} />}
        </section>
      ) : view === 'edit' ? (
        <EditInvoice L={L} fmt={fmt} perms={perms} onReceipt={setRc} hint={hint} />
      ) : view === 'gifts' ? (
        <Gifts L={L} fmt={fmt} perms={perms} shift={shift} hint={hint} />
      ) : view === 'coupons' ? (
        <Coupons L={L} fmt={fmt} />
      ) : view === 'eta' ? (
        <Eta L={L} fmt={fmt} />
) : view === 'approvals' ? (
        <Approvals L={L} fmt={fmt} />
      ) : view === 'returns' ? (
        <Returns L={L} branch={shift.branch} onReceipt={setRc} onExchange={(name) => { setView('sale'); applyReceipt(name); }} />
      ) : (
        <main>
          <section className="card cart">
            {promos.length > 0 && (
              <div className="promos" data-testid="promos"><b>{L('todayOffers')}: </b>
                {promos.map((p, i) => <span key={i} data-testid="promo-chip">{promoText(p, L)}</span>)}</div>)}
            <div className="picker" data-testid="customer-picker">
              <b>{L('customer')}: </b><span data-testid="customer-name">{customer ? customer.customer_name : L('cashCustomer')}</span>{' '}
              {customer && <button onClick={() => setCustomer(null)}>{L('cashCustomer')}</button>}{' '}
              <input value={custQ} onChange={(e) => setCustQ(e.target.value)} placeholder={L('changeCustomer') + ' ...'} data-testid="cust-search" />{' '}
              <button onClick={() => setNewCust({ name: '', phone: '' })} data-testid="cust-new">{L('newCustomer')}</button>
              {custList.length > 0 && <div className="drop">{custList.map((c) => <div key={c.name} data-testid="cust-opt" onClick={() => { setCustomer(c); setCustQ(''); setCustList([]); }}>{c.customer_name} {c.mobile_no || ''}</div>)}</div>}
              {newCust && <div className="card"><input placeholder={L('name')} value={newCust.name} onChange={(e) => setNewCust({ ...newCust, name: e.target.value })} data-testid="nc-name" />{' '}
                <input placeholder={L('phone')} value={newCust.phone} onChange={(e) => setNewCust({ ...newCust, phone: e.target.value })} data-testid="nc-phone" />{' '}
                <button className="primary" onClick={newCustomer} data-testid="nc-save">{L('save')}</button> <button onClick={() => setNewCust(null)}>{L('cancel')}</button></div>}
            </div>
            <form onSubmit={add}>
              <input autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder={L('scan')} data-testid="scan" />
              <button className="primary">{L('add')}</button>
            </form>
            {msg && <div className="msg" data-testid="msg">{msg}</div>}
            {!cart.length ? <p className="muted">{L('empty')}</p> : (
              <table><thead><tr><th></th><th>{L('qty')}</th><th>{L('price')}</th><th>{L('total')}</th><th /></tr></thead>
                <tbody>{cart.map((l, i) => { const q = quote && quote.lines[i]; return (
                  <tr key={l.itemId + i} data-testid="line"><td>{l.name}{q && q.promoNames && q.promoNames.length ? <small className="promo"> {L('promo')}: {q.promoNames.join(', ')}</small> : null}
                    {l.hasSerial && <div><input value={l.serials} placeholder={L('serials')} data-testid="serial-input" onChange={(e) => { const v = e.target.value; setCart(cart.map((x, k) => (k === i ? { ...x, serials: v, qty: Math.max(1, (v.split(/[\s,;]+/).filter(Boolean)).length) } : x))); }} /></div>}</td>
                    <td>{l.qty}</td><td>{fmt(l.price)}</td><td>{q ? fmt(q.net) : ''}</td>
                    <td><button onClick={() => setCart(cart.filter((_, k) => k !== i))}>{L('remove')}</button></td></tr>); })}</tbody></table>)}
          </section>
          <aside className="card pay">
            <div className="big" data-testid="total">{L('total')}: {fmt(total)}</div>
            {quote && quote.lines.some((l) => l.promoDisc > 0) && <div className="muted">{L('discount')}: {fmt(quote.lines.reduce((s, l) => s + l.promoDisc, 0))}</div>}
            <div data-testid="xr-box">
              {xr ? <div className="ok-box card" data-testid="xr-applied">{L('exchangeReceipt')} {xr.name}: {L('credit')} {fmt(xr.amount)} <button onClick={() => setXr(null)}>{L('remove')}</button></div>
                : <div><input value={xrCode} onChange={(e) => setXrCode(e.target.value)} placeholder={L('receiptNo')} data-testid="xr-code" /> <button onClick={() => applyReceipt(xrCode.trim().toUpperCase())} data-testid="xr-apply">{L('applyReceipt')}</button></div>}
            </div>
            <div data-testid="coupon-box">
              {couponCode ? <div className="ok-box card" data-testid="coupon-applied">🎟 {couponCode}: -{fmt(quote ? quote.coupon_disc || 0 : 0)} <button onClick={() => setCouponCode('')}>{L('remove')}</button></div>
                : <div><input value={couponIn} onChange={(e) => setCouponIn(e.target.value)} placeholder={L('cpEnter')} data-testid="coupon-code" dir="ltr" /> <button onClick={applyCoupon} disabled={!cart.length} data-testid="coupon-apply">{L('cpApply')}</button></div>}
            </div>
            <div data-testid="gift-box">
              {gift ? <div className="ok-box card" data-testid="gift-applied">🎁 <span dir="ltr">{gift.card_no}</span> · {L('giftBalance')} {fmt(gift.balance)} · {L('giftCovers')} <b data-testid="gift-covers">{fmt(giftCover)}</b>
                  {' '}<input value={giftAmt} onChange={(e) => setGiftAmt(e.target.value)} placeholder={L('giftUseAmt')} inputMode="decimal" data-testid="gift-amt" /> <button onClick={() => { setGift(null); setGiftAmt(''); }}>{L('remove')}</button></div>
                : <div><input value={giftNo} onChange={(e) => setGiftNo(e.target.value)} placeholder={L('giftUseNo')} data-testid="gift-no" dir="ltr" /> <button onClick={applyGift} data-testid="gift-apply">{L('giftCheck')}</button></div>}
            </div>
            {payCfg.providers.length > 0 && (
              <div data-testid="prov-box">
                {!prov ? payCfg.providers.map((pr) => (
                  <button key={pr} onClick={() => startProv(pr)} disabled={!cart.length || !(remaining > 0)} data-testid={'prov-' + pr}>{L('payWith')} {pr === 'paymob' ? 'Paymob' : 'Fawry'}</button>
                )) : (
                  <div className="ok-box card" data-testid="prov-attempt">
                    <div><b>{prov.provider === 'paymob' ? 'Paymob' : 'Fawry'}</b> · {fmt(prov.amount)} · <b data-testid="prov-state">{L('provState_' + prov.state)}</b></div>
                    {prov.instructions && <div className="muted" data-testid="prov-instructions">{prov.instructions}</div>}
                    {prov.checkout_url && <div><a href={prov.checkout_url} target="_blank" rel="noreferrer" data-testid="prov-checkout">{L('provCheckout')}</a></div>}
                    {prov.state === 'pending' && <span className="muted">{L('provPending')} </span>}
                    {prov.state === 'pending' && <button onClick={checkProv} data-testid="prov-check">{L('provCheck')}</button>}
                    {prov.state === 'pending' && payCfg.mode === 'mock' && <button onClick={settleProv} data-testid="prov-mock-paid">{L('provMockConfirm')}</button>}
                    <button onClick={() => { setProv(null); setProvTxn(''); }} data-testid="prov-remove">{L('remove')}</button>
                  </div>)}
              </div>)}
            <label>{L('cash')} <input value={cashPaid} onChange={(e) => setCashPaid(e.target.value)} inputMode="decimal" data-testid="cash" /></label>
            <label>{L('card')} <input value={cardPaid} onChange={(e) => setCardPaid(e.target.value)} inputMode="decimal" data-testid="card" /></label>
            {Number(cardPaid) > 0 && <label>{L('cardRef')} <input value={cardRef} onChange={(e) => setCardRef(e.target.value)} data-testid="card-ref" /></label>}
            <div>{L('remaining')}: {fmt(remaining)} · {L('change')}: {fmt(change)}</div>
            <span data-testid="pay-wrap" onClick={() => { if (canPay) return; hint(!cart.length ? 'EMPTY_CART' : !serialsOk ? 'SERIALS' : offlineBlock ? 'OFFLINE_PROMO' : 'UNDERPAID', offlineBlock); }}>
              <button className="primary" disabled={!canPay} style={canPay ? undefined : { pointerEvents: 'none' }} onClick={() => { closeGuide(); pay(); }} data-testid="pay">{L('pay')}</button></span>
            {' '}<label className="muted"><input type="checkbox" checked={!gOff} onChange={(e) => { setGuideOff(me, !e.target.checked); setGOff(!e.target.checked); }} data-testid="guide-switch" /> {L('guideOn')}</label>
            <hr />
            <button onClick={() => setCm({ direction: 'Out', amount: '', reason: '', manager: '', pin: '', needPin: false, err: '' })} data-testid="cash-out">{L('cashOut')}</button>
            <button onClick={() => setCm({ direction: 'In', amount: '', reason: '', manager: '', pin: '', needPin: false, err: '' })} data-testid="cash-in">{L('cashIn')}</button>
            {cm && (
              <div className="card" data-testid="cm-dialog">
                <h3>{cm.direction === 'Out' ? L('cashOut') : L('cashIn')}</h3>
                <label>{L('amount')} <input value={cm.amount} onChange={(e) => setCm({ ...cm, amount: e.target.value })} inputMode="decimal" data-testid="cm-amount" /></label>
                <label>{L('reason')} <input value={cm.reason} onChange={(e) => setCm({ ...cm, reason: e.target.value })} data-testid="cm-reason" /></label>
                {cm.needPin && <>
                  <label>{L('managerUser')} <input value={cm.manager} onChange={(e) => setCm({ ...cm, manager: e.target.value })} data-testid="cm-manager" /></label>
                  <label>{L('managerPin')} <input type="password" value={cm.pin} onChange={(e) => setCm({ ...cm, pin: e.target.value })} data-testid="cm-pin" /></label>
                </>}
                {cm.err && <div className="msg" data-testid="cm-err">{cm.err}</div>}
                <button className="primary" onClick={saveCashMove} data-testid="cm-save">{L('save')}</button>
                <button onClick={() => setCm(null)}>{L('cancel')}</button>
              </div>)}
            <hr />
            <GiftShiftBlock L={L} fmt={fmt} shift={shift} />
            <label>{L('countedCash')} <input value={counted} onChange={(e) => setCounted(e.target.value)} inputMode="decimal" data-testid="counted" /></label>
            <button onClick={closeShift} data-testid="close">{L('closeShift')}</button>
          </aside>
        </main>
      )}
      {rc && <Receipt data={rc} onClose={() => setRc(null)} />}
    </div>
  );
}

function promoText(p, L) {
  const where = p.scope ? ` (${p.scope})` : '';
  if (p.type === 'bxgy') return `${L('offerBuy')} ${p.buy} ${L('offerGet')} ${p.get}${where}`;
  if (p.type === 'bundle') return `${p.bundle_qty} = ${p.bundle_price}${where}`;
  if (p.type === 'percent') return `${p.name}: -${p.percent}%${where}`;
  if (p.type === 'amount') return `${p.name}: -${p.amount}${where}`;
  return p.name + where;
}

// Display-only fallback when the server cannot be reached; the server recomputes at submit time.
function localQuote(cart, promos) {
  // Same rules as the server (orbit_pos/logic/promotions.py), so the offline total matches what submit recomputes.
  const engine = (promos || []).map((p) => p.engine).filter(Boolean);
  const pr = applyPromotions(cart.map((l) => ({ itemId: l.itemId, group: l.group, qty: l.qty, price: l.price })), engine, new Date());
  return { lines: pr.lines, subtotal: pr.subtotal, invoice_discount: pr.invoicePromoDisc, invoice_promo_disc: pr.invoicePromoDisc,
           coupon_disc: 0, net_before_tax: pr2(pr.subtotal - pr.invoicePromoDisc), local: true };
}


// A close the manager sent back: the cashier counts the drawer again and saves the new count.
function Recounts({ L, fmt }) {
  const [rows, setRows] = useState([]); const [msg, setMsg] = useState('');
  const [cnt, setCnt] = useState({}); const [nt, setNt] = useState({});
  const load = async () => { try { setRows(await api('shift.my_recounts')); } catch (e) {} };
  useEffect(() => { load(); }, []);
  async function send(name) {
    setMsg('');
    try {
      await api('shift.recount_shift', { shift: name, counted_cash: cnt[name], note: nt[name] || '' });
      setMsg(L('recountDone')); setCnt({ ...cnt, [name]: '' }); setNt({ ...nt, [name]: '' }); load();
    } catch (e) { setMsg(fail(e)); }
  }
  if (!rows.length) return null;
  return (
    <section className="card" data-testid="recounts">
      <h3>{L('recountTitle')}</h3>
      {rows.map((r) => (
        <div key={r.name} className="ok-box card" data-testid={'recount-' + r.name}>
          <b>{r.name}</b>
          {r.approval_note && <p>{L('recountManagerNote')}: {r.approval_note}</p>}
          <label>{L('countedCash')} <input value={cnt[r.name] || ''} onChange={(e) => setCnt({ ...cnt, [r.name]: e.target.value })} inputMode="decimal" data-testid="recount-count" /></label>
          <label>{L('note')} <input value={nt[r.name] || ''} onChange={(e) => setNt({ ...nt, [r.name]: e.target.value })} data-testid="recount-note" /></label>
          <button className="primary" onClick={() => send(r.name)} data-testid="recount-send">{L('recountSend')}</button>
        </div>))}
      {msg && <div className="msg" data-testid="recount-msg">{msg}</div>}
    </section>
  );
}
