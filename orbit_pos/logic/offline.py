"""Idempotency for offline sync: a transaction id is accepted once."""
import hashlib


def make_txn_id(terminal: str, user: str, shift: str, counter: int, created_iso: str) -> str:
    raw = f"{terminal}|{user}|{shift}|{counter}|{created_iso}"
    return "T" + hashlib.sha256(raw.encode()).hexdigest()[:24]


class TxnRegistry:
    """In-memory model of the unique-index behaviour used by the Offline Transaction DocType."""
    def __init__(self):
        self.seen = {}

    def submit(self, txn_id: str, payload_hash: str):
        """Returns ('created'|'duplicate'|'conflict')."""
        if txn_id not in self.seen:
            self.seen[txn_id] = payload_hash
            return "created"
        return "duplicate" if self.seen[txn_id] == payload_hash else "conflict"
