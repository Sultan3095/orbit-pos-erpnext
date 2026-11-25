// Calls Frappe whitelisted methods. With ?mock=1 an in-memory mock runs the same contract (used for UI tests).
const M = 'orbit_pos.api.';
let csrf = () => (window.frappe && window.frappe.csrf_token) || (document.cookie.match(/csrf_token=([^;]+)/) || [])[1] || '';

async function real(method, args) {
  const res = await fetch('/api/method/' + M + method, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf() },
    body: JSON.stringify(args || {}),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = (j._server_messages && JSON.parse(JSON.parse(j._server_messages)[0]).message) || j.exception || msg; } catch (e) {}
    const err = new Error(msg); err.permanent = res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429; throw err;
  }
  return (await res.json()).message;
}

const CATALOG = {
  '6221': { name: 'Chips', price: 4, item_group: 'Snacks' }, '6222': { name: 'Juice', price: 12, item_group: 'Drinks' },
  '6223': { name: 'Water', price: 5, item_group: 'Drinks' },
};
const PROMOS = [{ name: 'Buy 2 get 3 chips', type: 'bxgy', itemId: '6221', buy: 2, get: 3 }];
function mockQuote(lines) {
  const out = lines.map((l) => ({ ...l, gross: l.qty * l.price, promoDisc: 0 }));
  PROMOS.forEach((p) => {
    const l = out.find((x) => x.itemId === p.itemId); if (!l) return;
    const free = Math.floor(Math.floor(l.qty) / (p.buy + p.get)) * p.get; l.promoDisc = free * l.price; l.promoNames = [p.name];
  });
  out.forEach((l) => { l.net = l.gross - l.promoDisc; });
  const subtotal = out.reduce((s, l) => s + l.net, 0);
  return { lines: out, subtotal, invoice_discount: 0, net_before_tax: subtotal };
}
let mockShift = null; const mockSeen = new Set(); let mockOnline = true;
export const setMockOnline = (v) => { mockOnline = v; };
async function mock(method, a) {
  if (!mockOnline) { const e = new Error('network'); throw e; }
  if (method === 'shift.current_shift') return mockShift;
  if (method === 'shift.open_shift') { if (mockShift) throw Object.assign(new Error('already open'), { permanent: true }); mockShift = { name: 'SHIFT-00001', status: 'Open', opening_cash: +a.opening_cash }; return mockShift; }
  if (method === 'shift.cash_movement') { if (a.direction === 'Out' && +a.amount > 200 && !a.pin) throw Object.assign(new Error('Manager approval required'), { permanent: true }); mockShift.cashOut = (mockShift.cashOut || 0) + (a.direction === 'Out' ? +a.amount : -+a.amount); return { name: 'CM-1', amount: +a.amount, direction: a.direction }; }
  if (method === 'shift.close_shift') { const z = { shift: mockShift.name, expected_cash: mockShift.opening_cash, counted_cash: +a.counted_cash, difference: +a.counted_cash - mockShift.opening_cash }; mockShift = null; return z; }
  if (method === 'sales.lookup') { const c = CATALOG[a.code]; if (!c) throw Object.assign(new Error('not found'), { permanent: true }); return { name: a.code, item_name: c.name, price: c.price, item_group: c.item_group, qty: 1 }; }
  if (method === 'sales.quote') return mockQuote(JSON.parse(a.payload).lines);
  if (method === 'sales.submit_sale') { const p = JSON.parse(a.payload); if (mockSeen.has(p.txn_id)) return { status: 'duplicate' }; mockSeen.add(p.txn_id); return { status: 'created', sales_invoice: 'SINV-' + mockSeen.size }; }
  throw new Error('mock: ' + method);
}
export const api = (method, args) => (new URLSearchParams(location.search).has('mock') ? mock : real)(method, args);
