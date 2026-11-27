// Calls Frappe whitelisted methods. With ?mock=1 an in-memory mock runs the same contract (used for UI tests).
const M = 'orbit_pos.api.';
// The POS page runs inside an iframe on the ERPNext desk: the CSRF token lives on the parent window, not in this frame.
let csrf = () => {
  try { if (window.frappe && window.frappe.csrf_token) return window.frappe.csrf_token; } catch (e) {}
  try { if (window.parent && window.parent.frappe && window.parent.frappe.csrf_token) return window.parent.frappe.csrf_token; } catch (e) {}
  return (document.cookie.match(/csrf_token=([^;]+)/) || [])[1] || '';
};

// Turns a raw server error into one short readable line: no HTML, no Python class path, no stack.
export function readable(m, status) {
  let x = String(m || '').replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&quot;/g, '"').replace(/&amp;/g, '&').trim();
  x = x.split('\n').filter(Boolean).pop() || x;
  x = x.replace(/^(?:[A-Za-z_]+\.)*[A-Za-z_]*(?:Error|Exception):\s*/, '');
  if (!x || x.length > 240) x = status === 403 ? 'You do not have permission for this action.' : status === 404 ? 'Not found.' : status >= 500 ? 'Server error. Try again; if it repeats call support.' : 'Something went wrong.';
  return x;
}
async function real(method, args) {
  const res = await fetch('/api/method/' + M + method, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf() },
    body: JSON.stringify(args || {}),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = (j._server_messages && JSON.parse(JSON.parse(j._server_messages)[0]).message) || j.exception || msg; } catch (e) {}
    msg = readable(msg, res.status);
    const err = new Error(msg); err.permanent = res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429; throw err;
  }
  return (await res.json()).message;
}

const CATALOG = {
  '6221': { name: 'Chips', price: 4, item_group: 'Snacks' }, '6222': { name: 'Juice', price: 12, item_group: 'Drinks' },
  '6223': { name: 'Water', price: 5, item_group: 'Drinks' },
  '7001': { name: 'Headphones', price: 250, item_group: 'Electronics', has_serial_no: 1 },
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
// Capture/demo persona: ?mock=1&persona=cashier shows the cashier view (recounts), default is the manager view (approvals).
const mockPersona = (typeof location !== 'undefined' ? new URLSearchParams(location.search).get('persona') : null) || 'manager';
const MANAGER_PERMS = { editInvoice: 'Y', voidInvoice: 'Y', sellGiftCard: 'Y', coupons: 'Y', viewOtherShifts: 'Y', approve: 'Y', seeExpected: 'Y', voidGiftCard: 'Y' };
const CASHIER_PERMS = { sellGiftCard: 'Y', coupons: 'Y' };
let mockProv = null; const mockReopened = new Set();
export const setMockOnline = (v) => { mockOnline = v; };
async function mock(method, a) {
  if (!mockOnline) { const e = new Error('network'); throw e; }
  if (method === 'shift.current_shift') return mockShift;
  if (method === 'shift.open_shift') { if (mockShift) throw Object.assign(new Error('already open'), { permanent: true }); mockShift = { name: 'SHIFT-00001', status: 'Open', opening_cash: +a.opening_cash }; return mockShift; }
  if (method === 'shift.cash_movement') { if (a.direction === 'Out' && +a.amount > 200 && !a.pin) throw Object.assign(new Error('Manager approval required'), { permanent: true }); mockShift.cashOut = (mockShift.cashOut || 0) + (a.direction === 'Out' ? +a.amount : -+a.amount); return { name: 'CM-1', amount: +a.amount, direction: a.direction }; }
  if (method === 'shift.close_shift') { const z = { shift: mockShift.name, expected_cash: mockShift.opening_cash, counted_cash: +a.counted_cash, difference: +a.counted_cash - mockShift.opening_cash }; mockShift = null; return z; }
  if (method === 'sales.lookup') { const c = CATALOG[a.code]; if (!c) throw Object.assign(new Error('not found'), { permanent: true }); return { name: a.code, item_name: c.name, price: c.price, item_group: c.item_group, qty: 1, ...(c.has_serial_no ? { has_serial_no: 1 } : {}) }; }
  if (method === 'sales.quote') { const qp = JSON.parse(a.payload); const qq = mockQuote(qp.lines); if (qp.coupon) qq.coupon_disc = Math.round(qq.subtotal * 0.10 * 100) / 100; return qq; }
  if (method === 'sales.submit_sale') { const p = JSON.parse(a.payload); if (p.lines.some((l) => l.qty === 77)) throw Object.assign(new Error('The price of 6223 is 5, not 1. Your role may not change prices'), { permanent: true }); if (mockSeen.has(p.txn_id)) return { status: 'duplicate' }; mockSeen.add(p.txn_id); return { status: 'created', sales_invoice: 'SINV-' + mockSeen.size }; }
  if (method === 'exchange.active_promotions') return [{ name: 'Buy 2 get 3 chips', type: 'bxgy', buy: 2, get: 3, scope: '6221' }];
  if (method === 'exchange.search_customers') return [];
  if (method === 'exchange.get_receipt') return { invoice: 'SINV-1', is_return: false, company: 'Mock', branch: '', date: '2026-01-01', time: '10:00', cashier: 'x', customer: 'عميل نقدي', lines: [], net_total: 0, discount: 0, taxes: [], grand_total: 0, payments: [], format: 'Standard 80mm', window_days: 14, terms_ar: '', terms_en: '' };
  if (method === 'payments.config') return { mode: 'mock', providers: ['paymob', 'fawry'] };
  if (method === 'payments.create_payment') { const p = JSON.parse(a.payload); mockProv = { name: 'PAY-00001', provider: a.provider, amount: p.amount, state: 'pending', instructions: a.provider === 'fawry' ? 'Fawry reference 99887766: the customer pays at any Fawry point' : '', checkout_url: a.provider === 'paymob' ? 'https://accept.paymob.com/unifiedcheckout/?token=demo' : '' }; return mockProv; }
  if (method === 'payments.payment_status') return mockProv;
  if (method === 'payments.mock_settle') { mockProv = { ...(mockProv || {}), state: a.state }; return mockProv; }
  if (method === 'shift.my_permissions') return { perms: mockPersona === 'cashier' ? CASHIER_PERMS : MANAGER_PERMS, user: mockPersona === 'cashier' ? 'cashier1' : 'manager1', theme: localStorage.getItem('orbit_theme') || 'light' };
  if (method === 'shift.pending_closes') return mockPersona === 'cashier' ? [] : [{ name: 'SHIFT-00042', user: 'cashier1', closed_at: '2026-11-27 18:32' }];
  if (method === 'shift.pending_close_view') return { shift: a.shift, expected_cash: 5240, counted_cash: 5180, difference: -60, note: 'Drawer felt light after the evening rush.', needs_second: true };
  if (method === 'shift.approve_close') return { shift: a.shift, expected_cash: 5240, counted_cash: 5180, difference: -60 };
  if (method === 'shift.send_back_for_recount') return { ok: true };
  if (method === 'shift.my_recounts') return mockPersona === 'cashier' ? [{ name: 'SHIFT-00039', approval_note: 'الفرق ٥٠ جنيه، عيد العد من فضلك' }] : [];
  if (method === 'shift.recount_shift') return { ok: true };
  if (method === 'eta.eta_list') return [{ name: 'ETA-0001', invoice: 'SINV-1', amount: 120, state: 'queued', long_id: '', error: '' }, { name: 'ETA-0002', invoice: 'SINV-2', amount: 87.5, state: 'accepted', long_id: 'ETA-8F3K2', error: '' }, { name: 'ETA-0003', invoice: 'SINV-3', amount: 42, state: 'rejected', long_id: '', error: 'Invalid TIN format' }];
  if (method === 'eta.eta_retry' || method === 'eta.eta_submit_all') return { ok: true };
  if (method === 'exchange.exchange_receipt_info') return { name: a.name, status: 'Open', amount: 4 };
  if (method === 'exchange.search_invoices') return [{ name: 'SINV-1', posting_date: '2026-11-27', customer_name: 'Walk-in Customer', grand_total: 32 }, { name: 'SINV-2', posting_date: '2026-11-26', customer_name: 'Mona Ali', grand_total: 560 }];
  if (method === 'exchange.invoice_for_return') return { invoice: a.invoice, customer_name: 'Walk-in Customer', date: '2026-11-27', needs_manager: false, age_days: 0, window_days: 14, lines: [
    { row: 1, item_code: '6221', item_name: 'Chips', qty: 5, returned: 0, left: 5, rate: 4, promo: true, has_serial: false },
    { row: 2, item_code: '6222', item_name: 'Juice', qty: 2, returned: 0, left: 2, rate: 12, promo: false, has_serial: false },
    { row: 3, item_code: '7001', item_name: 'Headphones', qty: 2, returned: 0, left: 2, rate: 250, promo: false, has_serial: true, serials: ['SN-001', 'SN-002'] }] };
  if (method === 'sales.create_return') { const items = JSON.parse(a.items); if (items.some((i) => (i.serial_no || []).includes('SN-XXX'))) throw Object.assign(new Error('Serial SN-XXX does not belong to this invoice'), { permanent: true }); return { return_invoice: 'RINV-1', refund: items.reduce((s, i) => s + i.qty, 0) * 4, exchange_receipt: a.mode === 'credit' ? 'XR-0001' : undefined }; }
  if (method === 'sales.invoice_for_edit') { const opened = a.invoice === 'SINV-2' || mockReopened.has(a.invoice); return { invoice: a.invoice, rev: 0, blockers: [], shift_open: opened, shift: 'SHIFT-00001', lines_locked: false, lines: [{ itemId: '6221', name: 'Chips', qty: 5, price: 4 }, { itemId: '6222', name: 'Juice', qty: 2, price: 12 }], payments: [{ method: 'Cash', amount: 20, ref: '' }, { method: 'Credit Card', amount: 8, ref: 'REF-99' }] }; }
  if (method === 'shift.reopen_shift') { mockReopened.add(a.shift); mockReopened.add('SINV-1'); return { ok: true }; }
  if (method === 'sales.edit_invoice') return { sales_invoice: a.invoice };
  if (method === 'sales.void_invoice') return { ok: true };
  if (method === 'gifts.list_gift_cards') return { cards: [{ card_no: 'GC-1001', initial: 500, balance: 500, expires_on: '2027-11-27', status: 'active' }, { card_no: 'GC-1002', initial: 200, balance: 65, expires_on: '2026-01-01', status: 'expired' }], liability: { open: 565, expired: 65, count: 2 } };
  if (method === 'gifts.gift_by_value') { const t = { sold: 10, used: 6, partly: 2, untouched: 2, open_count: 4, open_balance: 1500, expired_count: 1, expired_balance: 65, written_off_count: 1, written_off_total: 200 }; return { rows: [{ value: 500, ...t }], total: t }; }
  if (method === 'gifts.check_gift_card') return { card_no: a.card_no, balance: 500, status: 'active', expires_on: '2027-11-27' };
  if (method === 'gifts.sell_gift_card') return { card_no: a.card_no || 'GC-1003', balance: +a.amount };
  if (method === 'gifts.gift_card_history') return { card_no: a.card_no, balance: 400, log: [{ creation: '2026-11-20 12:00', kind: 'issue', amount: 500, balance: 500, ref: 'SINV-9' }, { creation: '2026-11-25 15:40', kind: 'redeem', amount: -100, balance: 400, ref: 'SINV-21' }] };
  if (method === 'gifts.print_gift_cards') return { cards: Array.from({ length: Math.min(8, +a.qty || 8) }, (_, i) => ({ card_no: 'GC-20' + String(i + 1).padStart(2, '0'), value: +a.value || 100 })), design: { accent: '#1BA39C', client_name: 'Orbit Store' } };
  if (method === 'gifts.write_off_gift_card' || method === 'gifts.void_gift_card' || method === 'gifts.extend_gift_card' || method === 'gifts.delete_coupon') return { ok: true };
  if (method === 'gifts.list_coupons') return [{ code: 'WELCOME10', kind: 'percent', value: 10, min_total: 100, used: 14, max_uses: 100, enabled: 1, start_date: '2026-11-01', end_date: '2026-12-31', max_per_customer: 1 }, { code: 'FLAT50', kind: 'amount', value: 50, min_total: 0, used: 3, max_uses: 0, enabled: 0 }];
  if (method === 'gifts.save_coupon') return { ok: true };
  if (method === 'gifts.shift_gift_block') return { by_value: [{ value: 500, count: 2, total: 1000 }], sold_cash: 1000, redeemed: 150 };
  throw new Error('mock: ' + method);
}
export const api = (method, args) => (new URLSearchParams(location.search).has('mock') ? mock : real)(method, args);
