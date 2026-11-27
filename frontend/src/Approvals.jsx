import { fail } from './guide.js';
import { useEffect, useState } from 'react';
import { api } from './api.js';

// Blind shift closes waiting for a manager. The approver sees expected vs counted, then approves.
export default function Approvals({ L, fmt, onDone }) {
  const [list, setList] = useState([]); const [sel, setSel] = useState(null); const [view, setView] = useState(null);
  const [note, setNote] = useState(''); const [msg, setMsg] = useState(''); const [z, setZ] = useState(null);
  const [sm, setSm] = useState(''); const [sp, setSp] = useState('');
  const load = async () => { try { setList(await api('shift.pending_closes')); } catch (e) { setMsg(fail(e)); } };
  useEffect(() => { load(); }, []);
  async function open(name) { setSel(name); setZ(null); setMsg(''); try { setView(await api('shift.pending_close_view', { shift: name })); } catch (e) { setMsg(fail(e)); } }
  async function approve() { try { setZ(await api('shift.approve_close', { shift: sel, note, second_manager: sm || undefined, second_pin: sp || undefined })); setView(null); setSel(null); setNote(''); setSm(''); setSp(''); load(); onDone && onDone(); } catch (e) { setMsg(fail(e)); } }
  async function sendBack() { try { await api('shift.send_back_for_recount', { shift: sel, note }); setView(null); setSel(null); setNote(''); setMsg(L('sentBack')); load(); } catch (e) { setMsg(fail(e)); } }
  return (
    <section className="card" data-testid="approvals">
      <h3>{L('pendingCloses')}</h3>
      {!list.length && !z && <p className="muted" data-testid="no-pending">{L('noPending')}</p>}
      {list.length > 0 && (<table><thead><tr><th>{L('shiftNo')}</th><th>{L('cashier')}</th><th>{L('closedAt')}</th><th /></tr></thead><tbody>
        {list.map((s) => (<tr key={s.name}><td>{s.name}</td><td>{s.user}</td><td>{String(s.closed_at || '').slice(0, 16)}</td>
          <td><button onClick={() => open(s.name)} data-testid={'pc-' + s.name}>{L('review')}</button></td></tr>))}</tbody></table>)}
      {view && (<div className="ok-box card" data-testid="close-view">
        <div className="big">{L('expected')}: <b data-testid="cv-expected">{fmt(view.expected_cash)}</b></div>
        <div className="big">{L('countedCash')}: <b data-testid="cv-counted">{fmt(view.counted_cash)}</b></div>
        <div className="big">{L('difference')}: <b data-testid="cv-diff">{fmt(view.difference)}</b></div>
        {view.note && <p>{view.note}</p>}
        <label>{L('note')} <input value={note} onChange={(e) => setNote(e.target.value)} data-testid="cv-note" /></label>
        {view.needs_second && <p className="muted" data-testid="cv-second-needed">{L('secondNeeded')}</p>}
        {view.needs_second && (<div><label>{L('secondManagerUser')} <input value={sm} onChange={(e) => setSm(e.target.value)} data-testid="cv-second-user" /></label>
        <label>{L('secondManagerPin')} <input type="password" value={sp} onChange={(e) => setSp(e.target.value)} inputMode="numeric" data-testid="cv-second-pin" /></label></div>)}
        <button onClick={approve} data-testid="cv-approve">{L('approveClose')}</button>
        <button onClick={sendBack} data-testid="cv-send-back">{L('sendBack')}</button>
      </div>)}
      {z && <pre data-testid="approved-z">{L('expected')}: {fmt(z.expected_cash)} / {L('countedCash')}: {fmt(z.counted_cash)} / {L('difference')}: {fmt(z.difference)}</pre>}
      {msg && <div className="msg">{msg}</div>}
    </section>
  );
}
