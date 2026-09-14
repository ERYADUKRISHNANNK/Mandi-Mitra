"""Tamper-evident procurement receipts.

Each completed procurement mints a receipt whose SHA-256 hash includes the
previous receipt's hash (per mandi) — a lightweight hash-chain giving the same
tamper-evidence story as a blockchain ledger without the operational overhead.
An admin endpoint can verify the whole chain at any time; any retro-edit of a
payload breaks every subsequent hash.
"""

import hashlib
import json

from .db import execute, now_iso, query, query_one


def _hash(payload: str, prev_hash: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{payload}".encode()).hexdigest()


def mint_receipt(ticket_row) -> dict | None:
    """Create a chained receipt for a completed ticket (idempotent)."""
    existing = query_one("SELECT * FROM receipts WHERE ticket_id = ?", (ticket_row["id"],))
    if existing:
        return dict(existing)

    from .pricing import procurement_amount
    payload = {
        "token": ticket_row["token"],
        "mandi_id": ticket_row["mandi_id"],
        "farmer": ticket_row["farmer_name"],
        "phone_tail": ticket_row["phone"][-4:],
        "crop": ticket_row["crop"],
        "quantity_kg": ticket_row["quantity_kg"],
        "quality_grade": ticket_row["quality_grade"],
        "amount": procurement_amount(ticket_row["crop"], ticket_row["quality_grade"] or "A", ticket_row["quantity_kg"]),
        "payment_status": "COMPLETED",
        "completed_at": ticket_row["completed_at"],
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    last = query_one(
        "SELECT hash FROM receipts WHERE mandi_id = ? ORDER BY id DESC LIMIT 1",
        (ticket_row["mandi_id"],),
    )
    prev_hash = last["hash"] if last else "GENESIS"
    digest = _hash(payload_json, prev_hash)

    execute(
        "INSERT INTO receipts (ticket_id, token, mandi_id, payload, prev_hash, hash, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_row["id"], ticket_row["token"], ticket_row["mandi_id"], payload_json, prev_hash, digest, now_iso()),
    )
    return query_one("SELECT * FROM receipts WHERE ticket_id = ?", (ticket_row["id"],))


def verify_chain(mandi_id: str | None = None) -> dict:
    """Recompute the chain and report the first broken link, if any."""
    if mandi_id:
        rows = query("SELECT * FROM receipts WHERE mandi_id = ? ORDER BY id", (mandi_id,))
    else:
        rows = query("SELECT * FROM receipts ORDER BY mandi_id, id")

    prev = {}
    broken = None
    checked = 0
    for r in rows:
        expected_prev = prev.get(r["mandi_id"], "GENESIS")
        if r["prev_hash"] != expected_prev:
            broken = {"receipt_id": r["id"], "token": r["token"], "reason": "prev_hash mismatch (records inserted or reordered)"}
            break
        if _hash(r["payload"], r["prev_hash"]) != r["hash"]:
            broken = {"receipt_id": r["id"], "token": r["token"], "reason": "payload hash mismatch (payload tampered)"}
            break
        prev[r["mandi_id"]] = r["hash"]
        checked += 1

    return {
        "verified": broken is None,
        "receipts_checked": checked,
        "mandis": len(prev),
        "broken_link": broken,
        "head_hashes": prev,
    }


def get_receipt(token: str) -> dict | None:
    row = query_one("SELECT * FROM receipts WHERE token = ?", (token,))
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d["payload"])
    return d
