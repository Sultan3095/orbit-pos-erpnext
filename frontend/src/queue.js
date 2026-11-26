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
    /** sales the server refused: [{payload, reason, at}]. They stay until someone retries or dismisses them. */
    failed() { return JSON.parse(storage.getItem(KEY + '_failed') || '[]').map((f) => (f && f.payload ? f : { payload: f, reason: '', at: '' })); },
    dismiss(txnId) { storage.setItem(KEY + '_failed', JSON.stringify(this.failed().filter((f) => f.payload.txn_id !== txnId))); },
    /** put a refused sale back in the queue (after the cause was fixed, e.g. the shift was reopened) */
    retry(txnId) { const f = this.failed(); const hit = f.find((x) => x.payload.txn_id === txnId); if (!hit) return false; this.push(hit.payload); this.dismiss(txnId); return true; },
    push(payload) { const q = load(); q.push(payload); save(q); return q.length; },
    /** send(payload) -> Promise<{status}>; stops at the first network failure, keeps order */
    async flush(send) {
      let sent = 0;
      for (;;) {
        const q = load();
        if (!q.length) break;
        let res;
        let reason = '';
        try { res = await send(q[0]); } catch (e) { if (e && e.permanent) { res = { status: 'rejected' }; reason = e.message || ''; } else break; }
        const rest = load().slice(1);
        if (res.status === 'rejected') {
          const failed = JSON.parse(storage.getItem(KEY + '_failed') || '[]'); failed.push({ payload: q[0], reason, at: new Date().toISOString() });
          storage.setItem(KEY + '_failed', JSON.stringify(failed));
        }
        save(rest); sent++;
      }
      return sent;
    },
  };
}
