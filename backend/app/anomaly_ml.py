"""AI module 3b — unsupervised anomaly layer.

Complements the rule engine with an IsolationForest over numeric features of
today's tickets (quantities, slot hours, concurrency). Flags outliers as
"SURVEY" severity for staff review — never automatic accusations. When
scikit-learn isn't available, degrades silently to rules-only.
"""

import numpy as np

from .db import query, today_str

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

CONTAMINATION = 0.12


def scan_unsupervised(mandi_id: str) -> list[dict]:
    if not SKLEARN_OK:
        return []
    rows = query(
        """
        SELECT token, phone, quantity_kg, slot_time, status,
               (SELECT COUNT(*) FROM tickets t2 WHERE t2.phone = t.phone
                  AND t2.slot_date = t.slot_date AND t2.status IN
                  ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')) AS concurrent
        FROM tickets t
        WHERE mandi_id = ? AND slot_date = ?
          AND status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT')
        """,
        (mandi_id, today_str()),
    )
    if len(rows) < 8:
        return []  # too few points for a meaningful isolation forest

    X = []
    for r in rows:
        try:
            hour = int(r["slot_time"].split(":")[0])
        except Exception:
            hour = 10
        X.append([float(r["quantity_kg"]), float(hour), float(r["concurrent"])])
    X = np.array(X)

    try:
        model = IsolationForest(n_estimators=64, contamination=CONTAMINATION, random_state=7)
        preds = model.fit_predict(X)
    except Exception:
        return []

    flags = []
    for r, p, feats in zip(rows, preds, X):
        if p == -1:
            flags.append({
                "type": "ML_OUTLIER",
                "severity": "SURVEY",
                "token": r["token"],
                "phone": r["phone"],
                "detail": (f"Unsupervised outlier: qty {int(feats[0])} kg, "
                           f"slot {int(feats[1])}:00, {int(feats[2])} concurrent booking(s)"),
                "recommendation": "Model-flagged pattern — routine verification suggested, not an accusation.",
            })
    return flags
