"""Auto barcodes (EAN-13 with check digit) and scale (weight) barcodes."""


def ean13_check_digit(first12: str) -> int:
    if len(first12) != 12 or not first12.isdigit():
        raise ValueError("need 12 digits")
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(first12))
    return (10 - s % 10) % 10


def make_ean13(seq: int, prefix: str = "200") -> str:
    """Internal-use EAN-13 (prefix 200-299 is reserved for in-store use)."""
    body = prefix + str(seq).zfill(12 - len(prefix))
    if len(body) != 12:
        raise ValueError("sequence too large")
    return body + str(ean13_check_digit(body))


def valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and int(code[-1]) == ean13_check_digit(code[:12])


def parse_scale_barcode(code: str, prefix: str = "21", plu_len: int = 5,
                        value_len: int = 5, mode: str = "weight", decimals: int = 3):
    """Weighed-item label, e.g. 21 PPPPP WWWWW C.
    mode 'weight': value is grams-style (decimals=3 -> kg), 'price': value is price*100."""
    if not valid_ean13(code) or not code.startswith(prefix):
        return None
    rest = code[len(prefix):-1]
    if len(rest) < plu_len + value_len:
        return None
    plu = rest[:plu_len]
    raw = int(rest[plu_len:plu_len + value_len])
    if mode == "weight":
        return {"plu": plu, "qty": raw / (10 ** decimals)}
    return {"plu": plu, "amount": raw / 100}
