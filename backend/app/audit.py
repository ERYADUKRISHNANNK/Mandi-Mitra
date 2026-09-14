"""Audit trail: every state-changing action is recorded for dispute resolution."""

import json

from .db import execute, now_iso


def log_event(mandi_id: str | None, actor: str, action: str, details: dict | None = None, ticket_id: int | None = None):
    execute(
        "INSERT INTO audit_events (ts, mandi_id, ticket_id, actor, action, details) VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), mandi_id, ticket_id, actor, action, json.dumps(details or {}, default=str)),
    )
