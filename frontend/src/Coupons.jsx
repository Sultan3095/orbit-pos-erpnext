import { useEffect, useState } from 'react';
import { api } from './api.js';

// Coupons for managers: percent or amount, minimum, dates, limits. The server checks every use.
const EMPTY = { code: '', kind: 'percent', value: '', min_total: '', start_date: '', end_date: '', max_uses: '', max_per_customer: '', enabled: 1 };
export default function Coupons({ L, fmt }) {
  const [list, setList] = useState([]); const [f, setF] = useState(null); const [msg, setMsg] = useState('');
  const load = async () => { try { setList(await api('gifts.list_coupons')); } catch (e) { setMsg(e.message); } };
  useEffect(() => { load(); }, []);
  async function save() { setMsg(''); try { await api('gifts.save_coupon', { data: JSON.stringify(f) }); setF(null); load(); } catch (e) { setMsg(e.message); } }
  async function del(code) { if (!window.confirm(L('deleteQ'))) return; try { await api('gifts.delete_coupon', { code }); load(); } catch (e) { setMsg(e.message); } }
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <section className="card" data-testid="coupons">
      <h2>🎟 {L('tabCoupons')}</h2>
      <p className="muted">{L('cpHelp')}</p>
      <button className="primary" data-testid="cp-add" onClick={() => setF({ ...EMPTY })}>+ {L('cpAdd')}</button>
      {msg && <div className="msg" data-testid="cp-msg">{msg}</div>}
      {f && (
        <div className="card" data-testid="cp-form">
          <label>{L('cpCode')} <input value={f.code} onChange={set('code')} data-testid="cf-code" dir="ltr" /></label>
          <label>{L('cpKind')} <select value={f.kind} onChange={set('kind')} data-testid="cf-kind"><option value="percent">{L('cpPercent')}</option><option value="amount">{L('cpAmount')}</option></select></label>
          <label>{L('cpValue')} <input value={f.value} onChange={set('value')} inputMode="decimal" data-testid="cf-value" /></label>
          <label>{L('cpMinTotal')} <input value={f.min_total} onChange={set('min_total')} inputMode="decimal" /></label>
          <label>{L('startDate')} <input type="date" value={f.start_date || ''} onChange={set('start_date')} /></label>
          <label>{L('endDate')} <input type="date" value={f.end_date || ''} onChange={set('end_date')} /></label>
          <label>{L('cpMaxUses')} <input value={f.max_uses} onChange={set('max_uses')} inputMode="numeric" /></label>
          <label>{L('cpMaxPerCustomer')} <input value={f.max_per_customer} onChange={set('max_per_customer')} inputMode="numeric" /></label>
          <label><input type="checkbox" checked={!!Number(f.enabled)} onChange={(e) => setF({ ...f, enabled: e.target.checked ? 1 : 0 })} /> {L('active')}</label>
          <button className="primary" onClick={save} data-testid="cf-save">{L('save')}</button> <button onClick={() => setF(null)}>{L('cancel')}</button>
        </div>)}
      <table><thead><tr><th>{L('cpCode')}</th><th>{L('cpKind')}</th><th>{L('cpValue')}</th><th>{L('cpMinTotal')}</th><th>{L('cpUsed')}</th><th>{L('active')}</th><th /></tr></thead>
        <tbody>{list.map((c) => (
          <tr key={c.code} data-testid="cp-row"><td dir="ltr"><b>{c.code}</b></td><td>{L(c.kind === 'percent' ? 'cpPercent' : 'cpAmount')}</td><td>{c.kind === 'percent' ? c.value + '%' : fmt(c.value)}</td>
            <td>{c.min_total ? fmt(c.min_total) : '-'}</td><td>{c.used}{c.max_uses ? ' / ' + c.max_uses : ''}</td><td>{c.enabled ? '✓' : '—'}</td>
            <td><button onClick={() => setF({ ...c, start_date: c.start_date || '', end_date: c.end_date || '' })}>{L('edit')}</button> <button onClick={() => del(c.code)}>{L('remove')}</button></td></tr>))}</tbody></table>
    </section>
  );
}
