// Offline queue. Every sale gets a unique txn_id once; retries resend the SAME payload,
// and the server returns "duplicate" instead of creating a second invoice.
export function newTxnId(terminal, counter, now = new Date()) {
  const rnd = Math.random().toString(36).slice(2, 10);
  return `${terminal}-${now.getTime().toString(36)}-${counter}-${rnd}`;
}

export function createQueue(storage) {
  const KEY = 'orbit_queue';
  const load = () => JSON.parse(storage.getItem(KEY) || '[]');
  const save = (q) => storage.setItem(KEY, JSON.stringify(q));
  return {
    list: load,
    push(payload) { const q = load(); q.push(payload); save(q); return q.length; },
    /** send(payload) -> Promise<{status}>; stops at the first network failure, keeps order */
    async flush(send) {
      let sent = 0;
      for (;;) {
        const q = load();
        if (!q.length) break;
        let res;
        try { res = await send(q[0]); } catch (e) { if (e && e.permanent) { res = { status: 'rejected' }; } else break; }
        const rest = load().slice(1);
        if (res.status === 'rejected') {
          const failed = JSON.parse(storage.getItem(KEY + '_failed') || '[]'); failed.push(q[0]);
          storage.setItem(KEY + '_failed', JSON.stringify(failed));
        }
        save(rest); sent++;
      }
      return sent;
    },
  };
}
