import { useState } from 'react';
import { api } from './api.js';

// Edit or void an invoice. A closed shift must first have its close cancelled (reopened) by an authorised user.
export default function EditInvoice({ L, fmt, perms, onReceipt }) {
  const [q, setQ] = useState(''); const [res, setRes] = useState([]); const [inv, setInv] = useState(null);
  const [qty, setQty] = useState({}); const [cash, setCash] = useState(''); const [card, setCard] = useState(''); const [ref, setRef] = useState('');
  const [reason, setReason] = useState(''); const [pin, setPin] = useState({ manager: '', pin: '' }); const [msg, setMsg] = useState('');
  const needPin = inv && !(perms.editInvoice === 'Y');
  async function search() { setMsg(''); try { setRes(await api('exchange.search_invoices', { q })); } catch (e) { setMsg(e.message); } }
  async function pick(name) {
    setMsg(''); try {
      const d = await api('sales.invoice_for_edit', { invoice: name }); setInv(d);
      setQty(Object.fromEntries(d.lines.map((l, i) => [i, l.qty])));
      const m = (k) => d.payments.filter((p) => p.method === k).reduce((a, p) => a + p.amount, 0);
      setCash(String(m('Cash'))); setCard(String(m('Credit Card') || 0)); setRef((d.payments.find((p) => p.ref) || {}).ref || '');
    } catch (e) { setMsg(e.message); }
  }
  const approver = () => (needPin ? { manager: pin.manager, pin: pin.pin } : {});
  async function reopen() { try { await api('shift.reopen_shift', { shift: inv.shift, reason, ...approver() }); setMsg(L('reopened')); await pick(inv.invoice); } catch (e) { setMsg(e.message); } }
  async function save() {
    const lines = inv.lines_locked ? inv.lines.map((l) => ({ itemId: l.itemId, qty: l.qty, price: l.price })) : inv.lines.map((l, i) => ({ itemId: l.itemId, qty: Number(qty[i]), price: l.price })).filter((l) => l.qty > 0);
    const payments = [{ method: 'Cash', amount: Number(cash) || 0 }, { method: 'Credit Card', amount: Number(card) || 0, ref }].filter((p) => p.amount > 0);
    try { const r = await api('sales.edit_invoice', { invoice: inv.invoice, payload: JSON.stringify({ lines, payments }), reason, ...approver() }); setMsg(L('edited') + ' ' + r.sales_invoice); setInv(null); setRes([]); if (onReceipt) onReceipt(await api('exchange.get_receipt', { invoice: r.sales_invoice })); }
    catch (e) { setMsg(e.message); }
  }
  async function voidIt() { try { await api('sales.void_invoice', { invoice: inv.invoice, reason, ...approver() }); setMsg(L('voided')); setInv(null); setRes([]); } catch (e) { setMsg(e.message); } }
  return (
    <section className="card" data-testid="edit-screen">
      <h3>{L('editTitle')}</h3>
      <form onSubmit={(e) => { e.preventDefault(); search(); }}><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={L('findSale')} data-testid="ed-q" /><button data-testid="ed-search">{L('search')}</button></form>
      {!inv && res.length > 0 && (<table><tbody>{res.map((r) => (<tr key={r.name}><td>{r.name}</td><td>{r.customer_name || ''}</td><td>{fmt(r.grand_total)}</td>
        <td><button onClick={() => pick(r.name)} data-testid={'ed-pick-' + r.name}>{L('editBtn')}</button></td></tr>))}</tbody></table>)}
      {inv && (<div data-testid="ed-form">
        <p>{inv.invoice} {inv.rev ? '· ' + L('revised') + ' ' + inv.rev : ''}</p>
        {inv.blockers.length > 0 && <p className="msg" data-testid="ed-blocked">{L('editBlocked')}: {inv.blockers.join(', ')}</p>}
        {!inv.shift_open && inv.blockers.length === 0 && (<div data-testid="ed-closed"><p className="msg">{L('shiftClosedMsg')}</p>
          <label>{L('reason')} <input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="ed-reason-reopen" /></label>
          <button onClick={reopen} data-testid="ed-reopen">{L('reopenClose')}</button></div>)}
        {inv.shift_open && inv.blockers.length === 0 && (<div>
          <table><thead><tr><th /><th>{L('qty')}</th><th>{L('price')}</th></tr></thead><tbody>
            {inv.lines.map((l, i) => (<tr key={i}><td>{l.name}</td><td>{inv.lines_locked ? l.qty : <input style={{ width: 70 }} value={qty[i]} onChange={(e) => setQty({ ...qty, [i]: e.target.value })} data-testid={'ed-qty-' + i} />}</td><td>{fmt(l.price)}</td></tr>))}</tbody></table>
          {inv.lines_locked && <p className="muted">{L('linesLocked')}</p>}
          <div className="row"><label>{L('cash')} <input value={cash} onChange={(e) => setCash(e.target.value)} data-testid="ed-cash" /></label>
            <label>{L('card')} <input value={card} onChange={(e) => setCard(e.target.value)} data-testid="ed-card" /></label>
            <label>{L('cardRef')} <input value={ref} onChange={(e) => setRef(e.target.value)} data-testid="ed-ref" /></label></div>
          <label>{L('reason')} <input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="ed-reason" /></label>
          {needPin && (<div><label>{L('managerUser')} <input value={pin.manager} onChange={(e) => setPin({ ...pin, manager: e.target.value })} data-testid="ed-mgr" /></label>
            <label>{L('managerPin')} <input type="password" value={pin.pin} onChange={(e) => setPin({ ...pin, pin: e.target.value })} data-testid="ed-pin" /></label></div>)}
          <button onClick={save} data-testid="ed-save">{L('save')}</button> <button onClick={voidIt} data-testid="ed-void">{L('voidInv')}</button></div>)}
        <button onClick={() => setInv(null)}>{L('cancel')}</button>
      </div>)}
      {msg && <div className="msg" data-testid="ed-msg">{msg}</div>}
    </section>
  );
}
