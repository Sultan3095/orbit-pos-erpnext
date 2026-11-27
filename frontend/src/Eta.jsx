import { fail } from './guide.js';
import { useEffect, useState } from 'react';
import { api } from './api.js';

// ETA tax receipts: every submitted sale becomes a receipt for the tax authority.
// This screen shows each receipt's state and lets a manager send the queued ones or resend a rejected one.
export default function Eta({ L, fmt }) {
  const [list, setList] = useState([]); const [msg, setMsg] = useState('');
  const load = async () => { try { setList(await api('eta.eta_list')); } catch (e) { setMsg(fail(e)); } };
  useEffect(() => { load(); }, []);
  async function submitAll() { setMsg(''); try { await api('eta.eta_submit_all'); load(); } catch (e) { setMsg(fail(e)); } }
  async function retry(name) { setMsg(''); try { await api('eta.eta_retry', { name }); load(); } catch (e) { setMsg(fail(e)); } }
  return (
    <section className="card" data-testid="eta">
      <h3>{L('etaTitle')}</h3>
      <p className="muted">{L('etaHelp')}</p>
      {list.length > 0 && <button onClick={submitAll} data-testid="eta-submit-all">{L('etaSubmitAll')}</button>}
      {!list.length && <p className="muted" data-testid="eta-none">{L('etaNone')}</p>}
      {list.length > 0 && (<table><thead><tr><th>{L('etaInvoice')}</th><th>{L('amount')}</th><th>{L('giftStatus')}</th><th>{L('etaLongId')}</th><th>{L('etaError')}</th><th /></tr></thead><tbody>
        {list.map((r) => (<tr key={r.name}><td>{r.invoice}</td><td>{fmt(r.amount)}</td>
          <td data-testid={'eta-state-' + r.invoice}>{L('etaState_' + r.state)}</td>
          <td className="muted">{r.long_id || ''}</td><td className="muted">{r.error || ''}</td>
          <td>{r.state === 'rejected' && <button onClick={() => retry(r.name)} data-testid={'eta-retry-' + r.invoice}>{L('etaRetry')}</button>}</td></tr>))}</tbody></table>)}
      {msg && <div className="msg">{msg}</div>}
    </section>
  );
}
