"""Two-terminal race test against a live bench site.

Fires the same money-moving operations from many parallel HTTP requests (the way two
terminals would) and checks the row locks hold:
  1. gift card: 8 parallel sales each want 25 from a 40 card -> exactly 1 wins, balance 15
  2. coupon max_uses=1: 6 parallel sales -> exactly 1 wins
  3. exchange receipt: 6 parallel redemptions of the same receipt -> exactly 1 wins
  4. same txn_id fired 6 times at once (double tap / retry) -> all succeed, ONE invoice

CI runs this after the UI capture step, while the bench is still up:
    python tools/concurrency_test.py /tmp/fixtures.json
Exits 1 if any check fails. Never run against a real site: it creates real invoices.
"""
import sys, json, threading, urllib.request, urllib.error, urllib.parse, http.cookiejar
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:8000"
SID = None
failures = []


def login():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"usr": "Administrator", "pwd": "admin"}).encode()
    op.open(BASE + "/api/method/login", data, timeout=30)
    return next(c.value for c in cj if c.name == "sid")


def call(method, **args):
    req = urllib.request.Request(BASE + "/api/method/" + method, data=urllib.parse.urlencode(args).encode(),
                                 headers={"Cookie": "sid=" + SID})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return True, json.loads(r.read().decode()).get("message")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()[:200]
        except Exception:
            body = ""
        return False, "HTTP %s %s" % (e.code, body)
    except Exception as e:
        return False, str(e)[:200]


def submit(payload):
    return call("orbit_pos.api.sales.submit_sale", payload=json.dumps(payload))


def race(name, payloads):
    bar = threading.Barrier(len(payloads))

    def one(p):
        bar.wait(timeout=60)
        return submit(p)

    with ThreadPoolExecutor(max_workers=len(payloads)) as ex:
        res = list(ex.map(one, payloads))
    won = [m for s, m in res if s]
    blocked = [m for s, m in res if not s]
    print("[%s] %d won, %d blocked" % (name, len(won), len(blocked)))
    for m in blocked[:2]:
        print("   blocked with:", str(m)[:160])
    return won, blocked


def sale(txn, shift, lines, **kw):
    return dict({"txn_id": txn, "shift": shift, "lines": lines, "payments": []}, **kw)


def expect(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def main():
    global SID
    fx = json.load(open(sys.argv[1]))
    sh = fx["shift"]
    SID = login()
    print("logged in; fixtures:", fx)

    water = lambda n: [{"itemId": "Water", "qty": n, "price": 5}]

    won, _ = race("gift card", [sale("RACE-GC-%d" % i, sh, water(5), gift_card=fx["card"], gift_amount=25)
                                for i in range(8)])
    expect(len(won) == 1, "gift card: exactly one of 8 parallel 25-pound redemptions won")
    s, card = call("orbit_pos.api.gifts.check_gift_card", card_no=fx["card"])
    bal = card.get("balance") if s and isinstance(card, dict) else None
    expect(s and bal is not None and abs(bal - 15) < 0.01,
           "gift card: balance 15 after the race (got %s)" % bal)

    won, _ = race("coupon", [sale("RACE-CPN-%d" % i, sh, water(4), coupon=fx["coupon"],
                                  payments=[{"method": "Cash", "amount": 18}]) for i in range(6)])
    expect(len(won) == 1, "coupon max_uses=1: exactly one of 6 parallel sales won")

    won, _ = race("exchange receipt", [sale("RACE-RC-%d" % i, sh, water(6), exchange_receipt=fx["receipt"])
                                       for i in range(6)])
    expect(len(won) == 1, "exchange receipt: exactly one of 6 parallel redemptions won")

    p = sale("RACE-DUP-1", sh, water(1), payments=[{"method": "Cash", "amount": 5}])
    won, blocked = race("same txn_id", [dict(p) for _ in range(6)])
    invs = {m.get("sales_invoice") for m in won if isinstance(m, dict)}
    expect(not blocked, "same txn_id: all 6 parallel retries succeeded (no duplicate-key error)")
    expect(len(invs) == 1, "same txn_id: one invoice for all retries (got %s)" % invs)

    print("\n%d check(s) failed" % len(failures) if failures else "\nAll two-terminal race checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
