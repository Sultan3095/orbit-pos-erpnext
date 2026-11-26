import { fail } from './guide.js';
import React, { useState } from 'react';
import { api } from './api.js';

const fmt = (n) => (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);

// Returns / exchange screen. The cashier never leaves the POS: find the sale, pick lines and serials,
// choose cash refund or an exchange receipt. Lines sold under a promotion are exchange only.
export default function Returns({ L, branch, onReceipt, onExchange }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState(null);
  const [inv, setInv] = useState(null);
  const [sel, setSel] = useState({});       // row -> { qty, serials: [] }
  const [mode, setMode] = useState('credit');
  const [mgr, setMgr] = useState({ user: '', pin: '' });
  const [msg, setMsg] = useState('');
  const [done, setDone] = useState(null);

  async function search(e) {
    e && e.preventDefault(); setMsg(''); setInv(null); setDone(null);
    try { setResults(await api('exchange.search_invoices', { q })); } catch (err) { setMsg(fail(err)); }
  }
  async function pick(name) {
    setMsg(''); setDone(null);
    try { const d = await api('exchange.invoice_for_return', { invoice: name }); setInv(d); setSel({}); setMode('credit'); }
    catch (err) { setMsg(fail(err)); }
  }
  async function reprint(name) { // any closed order, any time: same receipt, print button inside
    setMsg('');
    try { onReceipt(await api('exchange.get_receipt', { invoice: name })); } catch (err) { setMsg(fail(err)); }
  }
  const chosen = inv ? inv.lines.filter((l) => sel[l.row] && sel[l.row].qty > 0) : [];
  const hasPromo = chosen.some((l) => l.promo);
  const effMode = hasPromo ? 'credit' : mode;
  function setQty(l, v) {
    const qty = Math.max(0, Math.min(l.left, Number(v) || 0));
    setSel({ ...sel, [l.row]: { qty, serials: l.has_serial ? (sel[l.row] ? sel[l.row].serials.slice(0, qty) : []) : [] } });
  }
  function toggleSerial(l, sn) {
    const cur = sel[l.row] ? sel[l.row].serials : [];
    const next = cur.includes(sn) ? cur.filter((x) => x !== sn) : [...cur, sn];
    setSel({ ...sel, [l.row]: { qty: next.length, serials: next } });
  }
  const serialsOk = chosen.every((l) => !l.has_serial || sel[l.row].serials.length === sel[l.row].qty);
  const value = chosen.reduce((s, l) => s + l.rate * sel[l.row].qty, 0);

  async function confirm() {
    setMsg('');
    const items = chosen.map((l) => ({ item_code: l.item_code, row: l.row, qty: sel[l.row].qty, ...(l.has_serial ? { serial_no: sel[l.row].serials } : {}) }));
    try {
      const args = { invoice: inv.invoice, items: JSON.stringify(items), mode: effMode, current_branch: branch || undefined };
      if (inv.needs_manager) { args.manager = mgr.user; args.pin = mgr.pin; }
      const r = await api('sales.create_return', args);
      setDone(r); setInv(null); setResults(null);
      const rc = await api('exchange.get_receipt', { invoice: r.return_invoice });
      onReceipt(rc);
    } catch (err) { setMsg(fail(err)); }
  }

  return (
    <main className="returns" data-testid="returns-screen">
      <section className="card" style={{ gridColumn: '1 / -1' }}>
        <h2>{L('returnsTitle')}</h2>
        <form onSubmit={search}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={L('findSale')} data-testid="ret-search" />
          <button className="primary" data-testid="ret-find">{L('search')}</button>
        </form>
        {msg && <div className="msg" data-testid="ret-msg">{msg}</div>}
        {results && (results.length ? (
          <table><thead><tr><th>{L('invoice')}</th><th>{L('date')}</th><th>{L('customer')}</th><th>{L('total')}</th><th></th></tr></thead>
            <tbody>{results.map((r) => (
              <tr key={r.name} data-testid="inv-row" onClick={() => pick(r.name)} style={{ cursor: 'pointer' }}>
                <td>{r.name}</td><td>{r.posting_date}</td><td>{r.customer_name}</td><td>{fmt(r.grand_total)}</td>
                <td><button data-testid="inv-reprint" onClick={(e) => { e.stopPropagation(); reprint(r.name); }}>{L('reprint')}</button></td></tr>))}</tbody></table>
        ) : <p className="muted">{L('noResults')}</p>)}
        {done && (
          <div className="card ok-box" data-testid="ret-done">
            <b>{L('returnDone')}: {done.return_invoice}</b> — {L('value')}: {fmt(done.refund)}
            {done.exchange_receipt && <div>{L('exchangeReceipt')}: <b data-testid="ret-receipt-no">{done.exchange_receipt}</b>
              <button onClick={() => onExchange(done.exchange_receipt)} data-testid="ret-use-now">{L('exchangeNow')}</button></div>}
          </div>)}
      </section>
      {inv && (
        <section className="card" style={{ gridColumn: '1 / -1' }} data-testid="ret-invoice">
          <h3>{inv.invoice} — {inv.customer_name} — {inv.date}</h3>
          {inv.needs_manager && <div className="msg" data-testid="ret-window-warn">{L('afterWindow')} ({inv.age_days} / {inv.window_days} {L('days')})</div>}
          <table><thead><tr><th></th><th>{L('sold')}</th><th>{L('returned')}</th><th>{L('price')}</th><th>{L('returnQty')}</th></tr></thead>
            <tbody>{inv.lines.map((l, i) => (
              <React.Fragment key={l.row}>
                <tr data-testid="ret-line"><td>{l.item_name}{l.promo ? <small className="promo"> {L('exchangeOnly')}</small> : null}</td>
                  <td>{l.qty}</td><td>{l.returned}</td><td>{fmt(l.rate)}</td>
                  <td>{l.left > 0 ? <input style={{ width: 70 }} value={sel[l.row] ? sel[l.row].qty : ''} onChange={(e) => setQty(l, e.target.value)} inputMode="decimal" data-testid={'ret-qty-' + i} disabled={l.has_serial} /> : L('fullyReturned')}</td></tr>
                {l.has_serial && l.serials.length ? <tr><td colSpan="5">{L('pickSerials')}: {l.serials.map((sn) => (
                  <label key={sn} style={{ marginInlineEnd: 12 }}><input type="checkbox" checked={!!(sel[l.row] && sel[l.row].serials.includes(sn))} onChange={() => toggleSerial(l, sn)} data-testid={'serial-' + sn} /> {sn}</label>))}</td></tr> : null}
              </React.Fragment>))}</tbody></table>
          <div style={{ marginTop: 12 }}>
            <label><input type="radio" checked={effMode === 'credit'} onChange={() => setMode('credit')} data-testid="mode-credit" /> {L('modeCredit')}</label>{' '}
            <label><input type="radio" checked={effMode === 'refund'} disabled={hasPromo} onChange={() => setMode('refund')} data-testid="mode-refund" /> {L('modeRefund')}</label>
            {hasPromo && <div className="muted" data-testid="ret-promo-note">{L('promoNoRefund')}</div>}
          </div>
          {inv.needs_manager && <div style={{ marginTop: 8 }}>
            <input placeholder={L('managerUser')} value={mgr.user} onChange={(e) => setMgr({ ...mgr, user: e.target.value })} data-testid="ret-mgr" />{' '}
            <input type="password" placeholder={L('managerPin')} value={mgr.pin} onChange={(e) => setMgr({ ...mgr, pin: e.target.value })} data-testid="ret-pin" /></div>}
          <div className="big" data-testid="ret-value" style={{ marginTop: 10 }}>{L('value')}: {fmt(value)}</div>
          <button className="primary" disabled={!chosen.length || !serialsOk} onClick={confirm} data-testid="ret-confirm">{effMode === 'credit' ? L('issueExchange') : L('refundNow')}</button>
        </section>)}
    </main>
  );
}
