"""Simulated SMS/IVR gateway.

Production deployments swap send_sms/send_voice for a real telecom gateway;
call signatures and the notification log are unchanged, so only these two
functions need replacing.
"""

from .db import execute, now_iso, query, query_one
from .i18n import render

_relay_subscribers: list = []  # optional UI hook: callables receiving (row_dict)


def on_notify(callback):
    _relay_subscribers.append(callback)


def send_sms(phone: str, lang: str, template_key: str, ctx: dict, ticket_id=None):
    body = render(lang, template_key, ctx)
    execute(
        "INSERT INTO notifications (ticket_id, phone, channel, template_key, lang, body, simulated, created_at)"
        " VALUES (?, ?, 'SMS', ?, ?, ?, 1, ?)",
        (ticket_id, phone, template_key, lang, body, now_iso()),
    )
    _relay(template_key, body)


def send_voice(phone: str, lang: str, template_key: str, ctx: dict, ticket_id=None):
    body = render(lang, template_key, ctx)
    execute(
        "INSERT INTO notifications (ticket_id, phone, channel, template_key, lang, body, simulated, created_at)"
        " VALUES (?, ?, 'IVR', ?, ?, ?, 1, ?)",
        (ticket_id, phone, template_key, lang, body, now_iso()),
    )
    # Push the call to connected clients so the farmer's app RINGS and plays
    # it automatically (the simulated telecom gateway).
    if ticket_id:
        try:
            t = query_one("SELECT mandi_id, token FROM tickets WHERE id = ?", (ticket_id,))
            if t:
                from .events import broadcast_sync
                broadcast_sync(t["mandi_id"], "voice_call", {
                    "phone": phone, "token": t["token"], "template_key": template_key,
                    "body": body, "lang": lang,
                })
        except Exception:
            pass
    _relay(template_key, body)


def _relay(template_key: str, body: str):
    for cb in list(_relay_subscribers):
        try:
            cb({"template_key": template_key, "body": body})
        except Exception:
            pass


def recent(limit: int = 100):
    rows = query("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]
