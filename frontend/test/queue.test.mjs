import assert from 'node:assert/strict';
import { createQueue, newTxnId } from '../src/queue.js';
const mem = () => { const m = {}; return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; };
const ids = new Set(); for (let i = 0; i < 1000; i++) ids.add(newTxnId('T1', i)); assert.equal(ids.size, 1000);
// offline then online: keeps order, retries with the same payload, never loses a sale
const q = createQueue(mem()); q.push({ txn_id: 'a' }); q.push({ txn_id: 'b' });
let online = false; const seen = [];
const send = async (p) => { if (!online) throw new Error('net'); seen.push(p.txn_id); return { status: 'created' }; };
assert.equal(await q.flush(send), 0); assert.equal(q.list().length, 2);
online = true; assert.equal(await q.flush(send), 2); assert.deepEqual(seen, ['a', 'b']); assert.equal(q.list().length, 0);
// a network drop in the middle keeps the unsent sale
const q2 = createQueue(mem()); q2.push({ txn_id: 'x' }); q2.push({ txn_id: 'y' });
let n = 0; await q2.flush(async (p) => { if (n++ === 1) throw new Error('net'); return { status: 'created' }; });
assert.deepEqual(q2.list().map((p) => p.txn_id), ['y']);
// permanent rejection (e.g. 4xx) goes to the failed list instead of blocking the queue
const st = mem(); const q3 = createQueue(st); q3.push({ txn_id: 'bad' }); q3.push({ txn_id: 'ok' });
await q3.flush(async (p) => { if (p.txn_id === 'bad') throw Object.assign(new Error('x'), { permanent: true }); return { status: 'created' }; });
assert.equal(q3.list().length, 0); assert.equal(JSON.parse(st.getItem('orbit_queue_failed')).length, 1);
// a refused sale keeps its reason, can be retried or dismissed, and old-format failed rows still load
const q4 = createQueue(mem()); q4.push({ txn_id: 'r1' });
await q4.flush(async () => { throw Object.assign(new Error('Shift is not open'), { permanent: true }); });
assert.equal(q4.failed()[0].reason, 'Shift is not open'); assert.equal(q4.failed()[0].payload.txn_id, 'r1');
assert.ok(q4.retry('r1')); assert.equal(q4.failed().length, 0); assert.equal(q4.list()[0].txn_id, 'r1');
const old = mem(); old.setItem('orbit_queue_failed', JSON.stringify([{ txn_id: 'o1' }])); assert.equal(createQueue(old).failed()[0].payload.txn_id, 'o1');
console.log('queue tests passed');

// readable server errors
const { readable } = await import('../src/api.js');
assert.equal(readable('<div>Coupon <b>expired</b></div>'), 'Coupon expired');
assert.equal(readable('Traceback...\nfrappe.exceptions.ValidationError: Gift card is empty'), 'Gift card is empty');
assert.ok(readable('x'.repeat(500), 500).startsWith('Server error'));
console.log('readable errors ok');
