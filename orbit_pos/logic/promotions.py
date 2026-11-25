"""Pure promotion engine (no Frappe imports, so it is unit-testable anywhere).

Ported from the Orbit POS desktop build, same rules:
- A manual line discount replaces promotions on that line.
- Non-stackable promotions: the best single one per line wins.
- Stackable promotions add on top.
- buy X get Y: units are pooled across eligible lines; every complete group of
  (X + Y) units gives Y discounted units (cheapest first). "Buy 2 get 3" means
  every full group of 5 units gives 3 free.
"""
from datetime import date, datetime
from typing import Optional


def r2(x: float) -> float:
    # round half away from zero, like the desktop build
    s = -1 if x < 0 else 1
    return s * int(abs(x) * 100 + 0.5 + 1e-9) / 100


def promo_active(p: dict, now: Optional[datetime] = None) -> bool:
    if not p or p.get("active") is False:
        return False
    now = now or datetime.now()
    d = now.date().isoformat() if isinstance(now, datetime) else str(now)
    if p.get("start") and d < str(p["start"]):
        return False
    if p.get("end") and d > str(p["end"]):
        return False
    days = p.get("days")
    if days:
        # JS getDay(): Sunday=0 .. Saturday=6
        js_day = (now.weekday() + 1) % 7
        if js_day not in days:
            return False
    return True


def _in_scope(p: dict, line: dict) -> bool:
    s = p.get("scope") or {"type": "all"}
    t = s.get("type")
    if t == "all":
        return True
    if t == "item":
        return line.get("itemId") == s.get("value")
    if t == "group":
        groups = s.get("groups") or [s.get("value")]     # "groups" = the chosen group plus all its sub-groups
        return (line.get("group") or "") in groups
    return False


def _units(lines, elig):
    units = []
    for i in elig:
        whole = int(lines[i]["qty"] + 1e-9)
        units.extend({"i": i, "price": lines[i]["price"]} for _ in range(whole))
    return units


def _promo_vector(p: dict, lines: list) -> list:
    out = [0.0] * len(lines)
    elig = [i for i, l in enumerate(lines)
            if not l.get("noPromo") and l["qty"] > 0 and _in_scope(p, l)]
    if not elig:
        return out
    pr = p.get("params") or {}
    t = p.get("type")
    if t == "percent":
        for i in elig:
            out[i] = r2(lines[i]["qty"] * lines[i]["price"] * (pr.get("percent") or 0) / 100)
    elif t == "amount":
        for i in elig:
            out[i] = r2(min(lines[i]["price"], pr.get("amount") or 0) * lines[i]["qty"])
    elif t == "bxgy":
        buy = max(1, int(pr.get("buy") or 1))
        get = max(1, int(pr.get("get") or 1))
        get_pct = 100 if pr.get("getPct") is None else pr["getPct"]
        units = _units(lines, elig)
        free_count = (len(units) // (buy + get)) * get
        units.sort(key=lambda u: u["price"])
        for k in range(free_count):
            u = units[k]
            out[u["i"]] = r2(out[u["i"]] + u["price"] * get_pct / 100)
    elif t == "bundle":
        q = max(1, int(pr.get("qty") or 1))
        units = _units(lines, elig)
        units.sort(key=lambda u: -u["price"])
        for b in range(len(units) // q):
            grp = units[b * q:b * q + q]
            regular = sum(u["price"] for u in grp)
            off = max(0.0, r2(regular - (pr.get("price") or 0)))
            given = 0.0
            for k, u in enumerate(grp):
                part = r2(off - given) if k == len(grp) - 1 else r2(off * (u["price"] / regular))
                given = r2(given + part)
                out[u["i"]] = r2(out[u["i"]] + part)
    return out


def apply_promotions(lines: list, promos: list, now: Optional[datetime] = None) -> dict:
    """lines: [{itemId, group, qty, price, manualPct, manualAmt, noPromo}]"""
    act = [p for p in (promos or []) if promo_active(p, now)]
    L = []
    for l in lines:
        gross = r2(l["qty"] * l["price"])
        has_manual = (l.get("manualPct") or 0) > 0 or (l.get("manualAmt") or 0) > 0
        manual = r2(min(gross, (l.get("manualAmt") or 0) + gross * (l.get("manualPct") or 0) / 100)) if has_manual else 0.0
        L.append({**l, "gross": gross, "manualDisc": manual, "promoDisc": 0.0,
                  "promoNames": [], "noPromo": bool(l.get("noPromo")) or has_manual})
    item_promos = sorted([p for p in act if p.get("type") not in ("invoice_pct", "invoice_amt")],
                         key=lambda p: -(p.get("priority") or 0))
    best = [{"d": 0.0, "name": None} for _ in L]
    stack = [{"d": 0.0, "names": []} for _ in L]
    for p in item_promos:
        for i, d in enumerate(_promo_vector(p, L)):
            if d <= 0:
                continue
            if p.get("stackable"):
                stack[i]["d"] = r2(stack[i]["d"] + d)
                stack[i]["names"].append(p.get("name"))
            elif d > best[i]["d"]:
                best[i] = {"d": d, "name": p.get("name")}
    for i, l in enumerate(L):
        d = r2(best[i]["d"] + stack[i]["d"])
        names = ([best[i]["name"]] if best[i]["name"] else []) + stack[i]["names"]
        l["promoDisc"] = r2(min(l["gross"], d))
        l["promoNames"] = names
        l["net"] = r2(l["gross"] - l["promoDisc"] - l["manualDisc"])
    subtotal = r2(sum(l["net"] for l in L))
    inv_d, inv_names, best_inv = 0.0, [], {"d": 0.0, "name": None}
    for p in act:
        if p.get("type") not in ("invoice_pct", "invoice_amt"):
            continue
        pr = p.get("params") or {}
        if pr.get("minTotal") and subtotal < pr["minTotal"]:
            continue
        d = r2(subtotal * (pr.get("percent") or 0) / 100) if p["type"] == "invoice_pct" \
            else r2(min(subtotal, pr.get("amount") or 0))
        if p.get("stackable"):
            inv_d = r2(inv_d + d)
            inv_names.append(p.get("name"))
        elif d > best_inv["d"]:
            best_inv = {"d": d, "name": p.get("name")}
    if best_inv["name"]:
        inv_d = r2(inv_d + best_inv["d"])
        inv_names.append(best_inv["name"])
    return {"lines": L, "subtotal": subtotal,
            "invoicePromoDisc": min(subtotal, inv_d), "invoicePromoNames": inv_names}
