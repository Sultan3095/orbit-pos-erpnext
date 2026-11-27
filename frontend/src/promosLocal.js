// Offline promotion engine: a line-for-line port of orbit_pos/logic/promotions.py.
// Used only when the server cannot be reached, so the cashier sees real totals offline.
// The server still recomputes everything at submit time; this never decides what is booked.

export function r2(x) {
  const s = x < 0 ? -1 : 1;
  return s * Math.floor(Math.abs(x) * 100 + 0.5 + 1e-9) / 100;
}

export function promoActive(p, now) {
  if (!p || p.active === false) return false;
  now = now || new Date();
  const d = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
  if (p.start && d < String(p.start)) return false;
  if (p.end && d > String(p.end)) return false;
  if (p.days && p.days.length && p.days.indexOf(now.getDay()) < 0) return false;   // getDay(): Sunday=0, same numbering as the server
  return true;
}

function inScope(p, line) {
  const s = p.scope || { type: 'all' };
  if (s.type === 'all') return true;
  if (s.type === 'item') return line.itemId === s.value;
  if (s.type === 'group') return (s.groups || [s.value]).indexOf(line.group || '') >= 0;
  return false;
}

function units(lines, elig) {
  const out = [];
  elig.forEach((i) => { const whole = Math.floor(lines[i].qty + 1e-9); for (let k = 0; k < whole; k++) out.push({ i, price: lines[i].price }); });
  return out;
}

function promoVector(p, lines) {
  const out = lines.map(() => 0.0);
  const elig = lines.map((l, i) => i).filter((i) => !lines[i].noPromo && lines[i].qty > 0 && inScope(p, lines[i]));
  if (!elig.length) return out;
  const pr = p.params || {};
  if (p.type === 'percent') {
    elig.forEach((i) => { out[i] = r2(lines[i].qty * lines[i].price * (pr.percent || 0) / 100); });
  } else if (p.type === 'amount') {
    elig.forEach((i) => { out[i] = r2(Math.min(lines[i].price, pr.amount || 0) * lines[i].qty); });
  } else if (p.type === 'bxgy') {
    const buy = Math.max(1, Math.floor(pr.buy || 1)), get = Math.max(1, Math.floor(pr.get || 1));
    const getPct = pr.getPct == null ? 100 : pr.getPct;
    const u = units(lines, elig);
    const freeCount = Math.floor(u.length / (buy + get)) * get;
    u.sort((a, b) => a.price - b.price);
    for (let k = 0; k < freeCount; k++) out[u[k].i] = r2(out[u[k].i] + u[k].price * getPct / 100);
  } else if (p.type === 'bundle') {
    const q = Math.max(1, Math.floor(pr.qty || 1));
    const u = units(lines, elig);
    u.sort((a, b) => b.price - a.price);
    for (let b = 0; b < Math.floor(u.length / q); b++) {
      const grp = u.slice(b * q, b * q + q);
      const regular = grp.reduce((t, x) => t + x.price, 0);
      const off = Math.max(0.0, r2(regular - (pr.price || 0)));
      let given = 0.0;
      grp.forEach((x, k) => {
        const part = k === grp.length - 1 ? r2(off - given) : r2(off * (x.price / regular));
        given = r2(given + part);
        out[x.i] = r2(out[x.i] + part);
      });
    }
  }
  return out;
}

export function couponAmount(c, base) {
  if (!c || !(base > 0)) return 0.0;
  if (c.minTotal && base < c.minTotal) return 0.0;
  const d = c.kind === 'percent' ? base * Math.min(100, c.value || 0) / 100 : (c.value || 0);
  return r2(Math.min(base, d));
}

// lines: [{itemId, group, qty, price, manualPct?, manualAmt?, noPromo?}]; promos: engine dicts (active_promotions .engine)
export function applyPromotions(lines, promos, now, coupon) {
  const act = (promos || []).filter((p) => promoActive(p, now));
  const L = lines.map((l) => {
    const gross = r2(l.qty * l.price);
    const hasManual = (l.manualPct || 0) > 0 || (l.manualAmt || 0) > 0;
    const manual = hasManual ? r2(Math.min(gross, (l.manualAmt || 0) + gross * (l.manualPct || 0) / 100)) : 0.0;
    return Object.assign({}, l, { gross, manualDisc: manual, promoDisc: 0.0, promoNames: [], noPromo: !!l.noPromo || hasManual });
  });
  const itemPromos = act.filter((p) => p.type !== 'invoice_pct' && p.type !== 'invoice_amt').sort((a, b) => (b.priority || 0) - (a.priority || 0));
  const best = L.map(() => ({ d: 0.0, name: null }));
  const stack = L.map(() => ({ d: 0.0, names: [] }));
  itemPromos.forEach((p) => {
    promoVector(p, L).forEach((d, i) => {
      if (d <= 0) return;
      if (p.stackable) { stack[i].d = r2(stack[i].d + d); stack[i].names.push(p.name); }
      else if (d > best[i].d) best[i] = { d, name: p.name };
    });
  });
  L.forEach((l, i) => {
    const d = r2(best[i].d + stack[i].d);
    l.promoNames = (best[i].name ? [best[i].name] : []).concat(stack[i].names);
    l.promoDisc = r2(Math.min(l.gross, d));
    l.net = r2(l.gross - l.promoDisc - l.manualDisc);
  });
  const subtotal = r2(L.reduce((t, l) => t + l.net, 0));
  let invD = 0.0; const invNames = []; const bestInv = { d: 0.0, name: null };
  act.forEach((p) => {
    if (p.type !== 'invoice_pct' && p.type !== 'invoice_amt') return;
    const pr = p.params || {};
    if (pr.minTotal && subtotal < pr.minTotal) return;
    const d = p.type === 'invoice_pct' ? r2(subtotal * (pr.percent || 0) / 100) : r2(Math.min(subtotal, pr.amount || 0));
    if (p.stackable) { invD = r2(invD + d); invNames.push(p.name); }
    else if (d > bestInv.d) { bestInv.d = d; bestInv.name = p.name; }
  });
  if (bestInv.name) { invD = r2(invD + bestInv.d); invNames.push(bestInv.name); }
  let couponDisc = 0.0;
  if (coupon) {
    couponDisc = couponAmount(coupon, r2(subtotal - Math.min(subtotal, invD)));
    if (couponDisc > 0) { invD = r2(invD + couponDisc); invNames.push('Coupon ' + coupon.code); }
  }
  return { lines: L, subtotal, couponDisc, invoicePromoDisc: Math.min(subtotal, invD), invoicePromoNames: invNames };
}
