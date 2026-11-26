import { useEffect, useState } from 'react';
import { api } from './api.js';
import { sheetBody, SHEET_CSS, printSheet } from './giftCards.js';

// Cards sold in this shift per value, the cash part, and the non-cash redemptions: shown before the cashier closes the shift.
export function GiftShiftBlock({ L, fmt, shift }) {
  const [b, setB] = useState(null);
  useEffect(() => { api('gifts.shift_gift_block', { shift: shift.name }).then(setB).catch(() => setB(null)); }, [shift.name]);
  if (!b || (!b.by_value.length && !b.redeemed)) return null;
  return (
    <div className="card" data-testid="gift-close"><b>🎁 {L('giftShiftBlock')}</b>
      {b.by_value.length > 0 && <table><thead><tr><th>{L('giftValueCol')}</th><th>{L('giftSoldCol')}</th><th>{L('amount')}</th></tr></thead>
        <tbody>{b.by_value.map((r) => <tr key={r.value} data-testid="gift-close-row"><td>{fmt(r.value)}</td><td>{r.count}</td><td>{fmt(r.total)}</td></tr>)}</tbody></table>}
      {b.by_value.length > 0 && <div>{L('giftSoldCash')}: <b>{fmt(b.sold_cash)}</b></div>}
      <small className="muted">{L('giftRedeemedLine')}: {fmt(b.redeemed)}</small></div>);
}

// Gift cards: list, sell, check balance, history, extend, cancel (unused only). The server holds every rule.
export default function Gifts({ L, fmt, perms, shift }) {
  const [data, setData] = useState({ cards: [], liability: { open: 0, expired: 0, count: 0 } });
  const [q, setQ] = useState(''); const [msg, setMsg] = useState(''); const [form, setForm] = useState(null);
  const [hist, setHist] = useState(null); const [sold, setSold] = useState(null); const [chk, setChk] = useState('');
  const [chkRes, setChkRes] = useState(null);
  const [byVal, setByVal] = useState({ rows: [], total: {} }); const [wo, setWo] = useState(null); const [pf, setPf] = useState(null); const [sheet, setSheet] = useState(null);
  const load = async () => { try { setData(await api('gifts.list_gift_cards', { q })); setByVal(await api('gifts.gift_by_value', {})); } catch (e) { setMsg(e.message); } };
  useEffect(() => { load(); }, [q]);
  const mgr = perms.voidGiftCard === 'Y';
  async function sell() {
    setMsg('');
    try {
      const r = await api('gifts.sell_gift_card', { amount: form.amount, shift: shift.name, method: form.method, card_no: form.no || '', expires_days: form.days || 0, customer_name: form.customer || '', ref: form.ref || '' });
      setSold(r); setForm(null); load();
    } catch (e) { setMsg(e.message); }
  }
  async function check() { setMsg(''); setChkRes(null); try { setChkRes(await api('gifts.check_gift_card', { card_no: chk })); } catch (e) { setMsg(e.message); } }
  async function history(no) { try { setHist(await api('gifts.gift_card_history', { card_no: no })); } catch (e) { setMsg(e.message); } }
  async function cancel(no) { if (!window.confirm(L('giftVoidQ'))) return; try { await api('gifts.void_gift_card', { card_no: no, reason: 'cancelled' }); load(); } catch (e) { setMsg(e.message); } }
  async function extend(no) { const d = window.prompt(L('giftExpires') + ' (YYYY-MM-DD)'); if (d === null) return; try { await api('gifts.extend_gift_card', { card_no: no, new_date: d }); load(); } catch (e) { setMsg(e.message); } }
  async function writeOff() { setMsg(''); try { await api('gifts.write_off_gift_card', { card_no: wo.no, reason: wo.reason }); setWo(null); load(); } catch (e) { setMsg(e.message); } }
  async function makeCards() { setMsg(''); try { const r = await api('gifts.print_gift_cards', { value: pf.value, qty: pf.qty }); setSheet(r.cards); setPf(null); } catch (e) { setMsg(e.message); } }
  const cur = ''; const store = 'Orbit POS';
  const T = byVal.total || {};
  const two = (n, v) => <td>{n || 0}{n ? <small className="muted"> ({fmt(v)})</small> : null}</td>;
  const st = (s) => L('giftState_' + s);
  return (
    <section className="card" data-testid="gifts">
      <h2>🎁 {L('tabGifts')}</h2>
      <p className="muted">{L('giftHelp')}</p>
      <div className="cards3">
        <div className="card"><small>{L('giftLiabilityLine')}</small><b data-testid="gift-liability">{fmt(data.liability.open)}</b></div>
        <div className="card"><small>{L('giftCount')}</small><b>{data.liability.count}</b></div>
        <div className="card"><small>{L('giftExpiredLine')}</small><b>{fmt(data.liability.expired)}</b></div>
      </div>
      {byVal.rows.length > 0 && (
        <div className="card" data-testid="gift-denom"><h3>{L('giftByValue')}</h3>
          <table><thead><tr><th>{L('giftValueCol')}</th><th>{L('giftSoldCol')}</th><th>{L('giftUsedCol')}</th><th>{L('giftPartlyCol')}</th><th>{L('giftUntouchedCol')}</th><th>{L('giftOpenCol')}</th><th>{L('giftExpiredCol')}</th><th>{L('giftWrittenOffCol')}</th></tr></thead>
            <tbody>{byVal.rows.map((r) => <tr key={r.value} data-testid="gift-denom-row"><td><b>{fmt(r.value)}</b></td><td>{r.sold}</td><td>{r.used}</td><td>{r.partly}</td><td>{r.untouched}</td>{two(r.open_count, r.open_balance)}{two(r.expired_count, r.expired_balance)}{two(r.written_off_count, r.written_off_total)}</tr>)}
              <tr className="tot"><td><b>{L('total')}</b></td><td>{T.sold}</td><td>{T.used}</td><td>{T.partly}</td><td>{T.untouched}</td>{two(T.open_count, T.open_balance)}{two(T.expired_count, T.expired_balance)}{two(T.written_off_count, T.written_off_total)}</tr></tbody></table></div>)}
      <div>
        <button data-testid="gift-print-open" onClick={() => setPf({ value: '', qty: 8 })}>🖨 {L('giftPrintCards')}</button>{' '}
        <button className="primary" data-testid="gift-sell-open" onClick={() => setForm({ amount: '', method: 'Cash', no: '', days: '', customer: '', ref: '' })}>🎁 {L('giftSell')}</button>{' '}
        <input value={chk} onChange={(e) => setChk(e.target.value)} placeholder={L('giftNo')} data-testid="gift-check-no" />{' '}
        <button onClick={check} data-testid="gift-check">{L('giftCheck')}</button>{' '}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={L('search')} data-testid="gift-q" />
      </div>
      {chkRes && <div className="ok-box card" data-testid="gift-check-res"><b dir="ltr">{chkRes.card_no}</b> · {L('giftBalance')}: <b>{fmt(chkRes.balance)}</b> · {st(chkRes.status)}{chkRes.expires_on ? ' · ' + L('giftExpires') + ': ' + chkRes.expires_on : ''}</div>}
      {msg && <div className="msg" data-testid="gift-msg">{msg}</div>}
      {form && (
        <div className="card" data-testid="gift-form">
          <h3>{L('giftSell')}</h3>
          <label>{L('giftAmount')} <input value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} inputMode="decimal" data-testid="gf-amount" /></label>
          <label>{L('giftNo')} <input value={form.no} onChange={(e) => setForm({ ...form, no: e.target.value })} placeholder={L('giftNoHint')} data-testid="gf-no" /></label>
          <label>{L('giftExpiryDays')} <input value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} inputMode="numeric" data-testid="gf-days" /></label>
          <label>{L('giftCustomer')} <input value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} data-testid="gf-customer" /></label>
          <label>{L('giftPayMethod')} <select value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} data-testid="gf-method"><option value="Cash">{L('cash')}</option><option value="Credit Card">{L('card')}</option></select></label>
          <button className="primary" onClick={sell} data-testid="gf-save">{L('giftSell')}</button> <button onClick={() => setForm(null)}>{L('cancel')}</button>
        </div>)}
      {pf && (
        <div className="card" data-testid="gift-print-form"><h3>{L('giftPrintCards')}</h3><p className="muted">{L('giftPrintHelp')}</p>
          <label>{L('giftAmount')} <input value={pf.value} onChange={(e) => setPf({ ...pf, value: e.target.value })} inputMode="decimal" data-testid="gp-value" /></label>
          <label>{L('giftQty')} <input value={pf.qty} onChange={(e) => setPf({ ...pf, qty: e.target.value })} inputMode="numeric" data-testid="gp-qty" /></label>
          <button className="primary" onClick={makeCards} data-testid="gp-go">{L('giftSheetReady')}</button> <button onClick={() => setPf(null)}>{L('cancel')}</button></div>)}
      {sheet && (
        <div className="card" data-testid="gift-sheet"><b>{L('giftSheetReady')}</b> <button className="primary" onClick={() => printSheet(sheet, store, cur)} data-testid="gp-print">🖨 {L('giftPrintNow')}</button> <button onClick={() => setSheet(null)}>{L('close')}</button>
          <style>{SHEET_CSS}</style><div className="sheetprev" dangerouslySetInnerHTML={{ __html: sheetBody(sheet, store, cur) }} /></div>)}
      {wo && (
        <div className="card" data-testid="gift-wo-form"><h3>{L('giftWriteOff')} <span dir="ltr">{wo.no}</span></h3><p className="muted">{L('giftWriteOffHelp')}</p>
          <label>{L('reason')} <input value={wo.reason} onChange={(e) => setWo({ ...wo, reason: e.target.value })} data-testid="gw-reason" /></label>
          <button className="primary" onClick={writeOff} data-testid="gw-save">{L('giftWriteOff')}</button> <button onClick={() => setWo(null)}>{L('cancel')}</button></div>)}
      {sold && <div className="ok-box card" data-testid="gift-sold"><div className="big">{L('giftSold')}</div><b dir="ltr" data-testid="gift-sold-no">{sold.card_no}</b> · {fmt(sold.balance)} <button onClick={() => setSold(null)}>{L('close')}</button></div>}
      <table><thead><tr><th>{L('giftNo')}</th><th>{L('giftInitial')}</th><th>{L('giftBalance')}</th><th>{L('giftExpires')}</th><th>{L('giftStatus')}</th><th /></tr></thead>
        <tbody>{data.cards.map((c) => (
          <tr key={c.card_no} data-testid="gift-row"><td dir="ltr">{c.card_no}</td><td>{fmt(c.initial)}</td><td><b>{fmt(c.balance)}</b></td><td>{c.expires_on || L('giftNever')}</td><td>{st(c.status)}</td>
            <td><button onClick={() => history(c.card_no)} data-testid={'gh-' + c.card_no}>{L('giftHistory')}</button>
              {mgr && c.status === 'expired' && c.balance > 0 && <> <button onClick={() => setWo({ no: c.card_no, reason: '' })} data-testid={'gw-' + c.card_no}>{L('giftWriteOff')}</button></>}
              {mgr && c.status !== 'void' && c.status !== 'writtenoff' && <> <button onClick={() => extend(c.card_no)} data-testid={'ge-' + c.card_no}>{L('giftExtend')}</button> <button onClick={() => cancel(c.card_no)} data-testid={'gv-' + c.card_no}>{L('giftVoid')}</button></>}</td></tr>))}</tbody></table>
      {hist && (
        <div className="card" data-testid="gift-history"><h3>{L('giftHistory')} <span dir="ltr">{hist.card_no}</span> · {L('giftBalance')}: {fmt(hist.balance)}</h3>
          <table><thead><tr><th>{L('time')}</th><th>{L('type')}</th><th>{L('amount')}</th><th>{L('giftBalance')}</th><th /></tr></thead>
            <tbody>{hist.log.map((x, i) => <tr key={i}><td>{String(x.creation).slice(0, 16)}</td><td>{L('giftLog_' + x.kind)}</td><td>{fmt(x.amount)}</td><td>{fmt(x.balance)}</td><td>{x.ref}</td></tr>)}</tbody></table>
          <button onClick={() => setHist(null)}>{L('close')}</button></div>)}
    </section>
  );
}
