import { useEffect, useState } from 'react';
import { api } from './api.js';

// Gift cards: list, sell, check balance, history, extend, cancel (unused only). The server holds every rule.
export default function Gifts({ L, fmt, perms, shift }) {
  const [data, setData] = useState({ cards: [], liability: { open: 0, expired: 0, count: 0 } });
  const [q, setQ] = useState(''); const [msg, setMsg] = useState(''); const [form, setForm] = useState(null);
  const [hist, setHist] = useState(null); const [sold, setSold] = useState(null); const [chk, setChk] = useState('');
  const [chkRes, setChkRes] = useState(null);
  const load = async () => { try { setData(await api('gifts.list_gift_cards', { q })); } catch (e) { setMsg(e.message); } };
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
      <div>
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
      {sold && <div className="ok-box card" data-testid="gift-sold"><div className="big">{L('giftSold')}</div><b dir="ltr" data-testid="gift-sold-no">{sold.card_no}</b> · {fmt(sold.balance)} <button onClick={() => setSold(null)}>{L('close')}</button></div>}
      <table><thead><tr><th>{L('giftNo')}</th><th>{L('giftInitial')}</th><th>{L('giftBalance')}</th><th>{L('giftExpires')}</th><th>{L('giftStatus')}</th><th /></tr></thead>
        <tbody>{data.cards.map((c) => (
          <tr key={c.card_no} data-testid="gift-row"><td dir="ltr">{c.card_no}</td><td>{fmt(c.initial)}</td><td><b>{fmt(c.balance)}</b></td><td>{c.expires_on || L('giftNever')}</td><td>{st(c.status)}</td>
            <td><button onClick={() => history(c.card_no)} data-testid={'gh-' + c.card_no}>{L('giftHistory')}</button>
              {mgr && c.status !== 'void' && <> <button onClick={() => extend(c.card_no)}>{L('giftExtend')}</button> <button onClick={() => cancel(c.card_no)} data-testid={'gv-' + c.card_no}>{L('giftVoid')}</button></>}</td></tr>))}</tbody></table>
      {hist && (
        <div className="card" data-testid="gift-history"><h3>{L('giftHistory')} <span dir="ltr">{hist.card_no}</span> · {L('giftBalance')}: {fmt(hist.balance)}</h3>
          <table><thead><tr><th>{L('time')}</th><th>{L('type')}</th><th>{L('amount')}</th><th>{L('giftBalance')}</th><th /></tr></thead>
            <tbody>{hist.log.map((x, i) => <tr key={i}><td>{String(x.creation).slice(0, 16)}</td><td>{L('giftLog_' + x.kind)}</td><td>{fmt(x.amount)}</td><td>{fmt(x.balance)}</td><td>{x.ref}</td></tr>)}</tbody></table>
          <button onClick={() => setHist(null)}>{L('close')}</button></div>)}
    </section>
  );
}
