import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { t } from './i18n.js';
import { api } from './api.js';
import { createQueue, newTxnId } from './queue.js';

const queue = createQueue(window.localStorage);
const TERMINAL = localStorage.getItem('orbit_terminal') || (localStorage.setItem('orbit_terminal', 'T' + Math.random().toString(36).slice(2, 6)), localStorage.getItem('orbit_terminal'));
const fmt = (n) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);

export default function App() {
  const [lang, setLang] = useState(localStorage.getItem('orbit_lang') || 'ar');
  const [theme, setTheme] = useState(localStorage.getItem('orbit_theme') || 'light');
  const [shift, setShift] = useState(null);
  const [cart, setCart] = useState([]);
  const [quote, setQuote] = useState(null);
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState('');
  const [cashPaid, setCashPaid] = useState('');
  const [cardPaid, setCardPaid] = useState('');
  const [opening, setOpening] = useState('0');
  const [counted, setCounted] = useState('');
  const [z, setZ] = useState(null);
  const [cm, setCm] = useState(null);   // cash in/out dialog state
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(queue.list().length);
  const counter = useRef(Number(localStorage.getItem('orbit_counter') || 0));
  const L = (k) => t(lang, k);

  useEffect(() => {
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = lang; document.documentElement.dataset.theme = theme;
    localStorage.setItem('orbit_lang', lang); localStorage.setItem('orbit_theme', theme);
  }, [lang, theme]);

  const refreshShift = useCallback(async () => { try { setShift(await api('shift.current_shift')); setOnline(true); } catch (e) { setOnline(false); } }, []);
  useEffect(() => { refreshShift(); }, [refreshShift]);

  const flush = useCallback(async () => {
    try {
      await queue.flush((p) => api('sales.submit_sale', { payload: JSON.stringify(p) }));
      setOnline(true);
    } catch (e) { setOnline(false); }
    setPending(queue.list().length);
  }, []);
  useEffect(() => { const id = setInterval(flush, 15000); window.addEventListener('online', flush); return () => { clearInterval(id); window.removeEventListener('online', flush); }; }, [flush]);

  // The server prices the cart (promotions, discounts). The client only displays the result.
  useEffect(() => {
    if (!cart.length) { setQuote(null); return; }
    let live = true;
    api('sales.quote', { payload: JSON.stringify({ lines: cart.map(({ itemId, group, qty, price }) => ({ itemId, group, qty, price })) }) })
      .then((q) => { if (live) setQuote(q); }).catch(() => { if (live) setQuote(localQuote(cart)); });
    return () => { live = false; };
  }, [cart]);

  const total = quote ? quote.net_before_tax : 0;
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
    try {
      const it = await api('sales.lookup', { code: c });
      setCart((cur) => {
        const i = cur.findIndex((x) => x.itemId === it.name && !it.orbit_weighed);
        const q = qty * (it.qty || 1);
        if (i >= 0) return cur.map((x, k) => (k === i ? { ...x, qty: x.qty + q } : x));
        return [...cur, { itemId: it.name, name: it.item_name, group: it.item_group, price: it.price, qty: q }];
      });
      setCode('');
    } catch (err) { setMsg(L('notFound') + ': ' + c); }
  }

  const paid = (Number(cashPaid) || 0) + (Number(cardPaid) || 0);
  const remaining = Math.max(0, total - paid);
  const change = Math.max(0, paid - total);
  const canPay = cart.length && quote && paid + 0.005 >= total && shift;

  async function pay() {
    counter.current += 1; localStorage.setItem('orbit_counter', String(counter.current));
    const cash = Number(cashPaid) || 0, card = Number(cardPaid) || 0;
    const payments = [];
    if (cash) payments.push({ method: 'Cash', amount: cash });
    if (card) payments.push({ method: 'Credit Card', amount: card });
    const payload = { txn_id: newTxnId(TERMINAL, counter.current), terminal: TERMINAL, shift: shift.name,
      lines: cart.map(({ itemId, group, qty, price }) => ({ itemId, group, qty, price })), payments };
    queue.push(payload); setPending(queue.list().length);       // always queue first, so nothing is lost
    setCart([]); setCashPaid(''); setCardPaid(''); setMsg(L('done') + (change ? ` — ${L('change')}: ${fmt(change)}` : ''));
    await flush();
  }

  async function openShift() { try { setShift(await api('shift.open_shift', { pos_profile: localStorage.getItem('orbit_profile') || 'POS', opening_cash: opening, terminal: TERMINAL })); } catch (e) { setMsg(e.message); } }
  async function saveCashMove() {
    const amount = Number(cm.amount);
    if (!(amount > 0)) { setCm({ ...cm, err: L('invalidAmount') }); return; }
    if (!cm.reason.trim()) { setCm({ ...cm, err: L('reasonRequired') }); return; }
    try {
      const args = { shift: shift.name, direction: cm.direction, amount, reason: cm.reason.trim() };
      if (cm.needPin) { args.manager = cm.manager; args.pin = cm.pin; }
      await api('shift.cash_movement', args);
      setMsg((cm.direction === 'Out' ? L('cashOut') : L('cashIn')) + ': ' + fmt(amount) + ' — ' + cm.reason.trim()); setCm(null);
    } catch (e) {
      const needs = /approval required|manager|PIN/i.test(e.message || '');
      setCm({ ...cm, needPin: cm.needPin || needs, err: e.message });
    }
  }
  async function closeShift() { try { setZ(await api('shift.close_shift', { shift: shift.name, counted_cash: counted })); setShift(null); } catch (e) { setMsg(e.message); } }

  return (
    <div className="app">
      <header>
        <b>{L('app')}</b>
        <span className={'pill ' + (online ? 'ok' : 'bad')} data-testid="net">{online ? L('online') : L('offline')}</span>
        <span className="pill" data-testid="pending">{L('queued')}: {pending}</span>
        <button onClick={flush}>{L('sync')}</button>
        <span className="sp" />
        <label>{L('theme')} <select value={theme} onChange={(e) => setTheme(e.target.value)} data-testid="theme">
          {['light', 'dark', 'blue'].map((x) => <option key={x} value={x}>{L(x)}</option>)}</select></label>
        <label>{L('lang')} <select value={lang} onChange={(e) => setLang(e.target.value)} data-testid="lang"><option value="ar">العربية</option><option value="en">English</option></select></label>
        <a href="#display" target="_blank" rel="noreferrer">{L('customerScreen')}</a>
      </header>

      {!shift ? (
        <section className="card" data-testid="noshift">
          <h2>{L('noShift')}</h2>
          <label>{L('openingCash')} <input value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" /></label>
          <button className="primary" onClick={openShift} data-testid="open">{L('openShift')}</button>
          {z && <pre data-testid="z">{L('expected')}: {fmt(z.expected_cash)} / {L('countedCash')}: {fmt(z.counted_cash)} / {L('difference')}: {fmt(z.difference)}</pre>}
        </section>
      ) : (
        <main>
          <section className="card cart">
            <form onSubmit={add}>
              <input autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder={L('scan')} data-testid="scan" />
              <button className="primary">{L('add')}</button>
            </form>
            {msg && <div className="msg" data-testid="msg">{msg}</div>}
            {!cart.length ? <p className="muted">{L('empty')}</p> : (
              <table><thead><tr><th></th><th>{L('qty')}</th><th>{L('price')}</th><th>{L('total')}</th><th /></tr></thead>
                <tbody>{cart.map((l, i) => { const q = quote && quote.lines[i]; return (
                  <tr key={l.itemId + i} data-testid="line"><td>{l.name}{q && q.promoNames && q.promoNames.length ? <small className="promo"> {L('promo')}: {q.promoNames.join(', ')}</small> : null}</td>
                    <td>{l.qty}</td><td>{fmt(l.price)}</td><td>{q ? fmt(q.net) : ''}</td>
                    <td><button onClick={() => setCart(cart.filter((_, k) => k !== i))}>{L('remove')}</button></td></tr>); })}</tbody></table>)}
          </section>
          <aside className="card pay">
            <div className="big" data-testid="total">{L('total')}: {fmt(total)}</div>
            {quote && quote.lines.some((l) => l.promoDisc > 0) && <div className="muted">{L('discount')}: {fmt(quote.lines.reduce((s, l) => s + l.promoDisc, 0))}</div>}
            <label>{L('cash')} <input value={cashPaid} onChange={(e) => setCashPaid(e.target.value)} inputMode="decimal" data-testid="cash" /></label>
            <label>{L('card')} <input value={cardPaid} onChange={(e) => setCardPaid(e.target.value)} inputMode="decimal" data-testid="card" /></label>
            <div>{L('remaining')}: {fmt(remaining)} · {L('change')}: {fmt(change)}</div>
            <button className="primary" disabled={!canPay} onClick={pay} data-testid="pay">{L('pay')}</button>
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
            <label>{L('countedCash')} <input value={counted} onChange={(e) => setCounted(e.target.value)} inputMode="decimal" data-testid="counted" /></label>
            <button onClick={closeShift} data-testid="close">{L('closeShift')}</button>
          </aside>
        </main>
      )}
    </div>
  );
}

// Display-only fallback when the server cannot be reached; the server recomputes at submit time.
function localQuote(cart) {
  const lines = cart.map((l) => ({ ...l, gross: l.qty * l.price, promoDisc: 0, net: l.qty * l.price }));
  const subtotal = lines.reduce((s, l) => s + l.net, 0);
  return { lines, subtotal, invoice_discount: 0, net_before_tax: subtotal };
}
