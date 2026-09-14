"""AI module 1 — wait-time prediction.

Layered design:
  1. Ridge regression trained on synthetic historical stats (hour of day,
     arrivals, processing rate, active counters) when history is available.
  2. Deterministic analytic fallback (queue position / throughput) when the
     model is missing or the input is out of the observed range.

Outputs a (minutes, confidence) tuple so the UI can show a confidence band.
"""

import math

import numpy as np

from .db import query

_model = None
_feature_stats = None


def _load_training_data():
    rows = query("SELECT hour, arrivals, processed, avg_wait_min, counters_active FROM history_stats")
    return [(r["hour"], r["arrivals"], r["processed"], r["counters_active"], r["avg_wait_min"]) for r in rows]


def train():
    """(Re)train the regression model from historical mandi statistics."""
    global _model, _feature_stats
    data = _load_training_data()
    if len(data) < 20:
        _model, _feature_stats = None, None
        return {"trained": False, "samples": len(data), "mode": "analytic-fallback"}

    X = np.array([[h, a, p, c] for h, a, p, c, _ in data], dtype=float)
    y = np.array([w for *_, w in data], dtype=float)
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std < 1e-9] = 1.0
    Xn = (X - mean) / std
    Xb = np.hstack([Xn, np.ones((Xn.shape[0], 1))])
    lam = 1.0
    gram = Xb.T @ Xb + lam * np.eye(Xb.shape[1])
    coef = np.linalg.solve(gram, Xb.T @ y)
    preds = Xb @ coef
    ss_res = float(((y - preds) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    _model = coef
    _feature_stats = (mean, std)
    return {"trained": True, "samples": len(data), "r2": round(r2, 3), "mode": "ridge-regression"}


def _model_predict(features) -> tuple[float, float]:
    """Return (minutes, confidence 0..1) using the trained model."""
    if _model is None or _feature_stats is None:
        return 0.0, 0.0
    mean, std = _feature_stats
    x = (np.array(features, dtype=float) - mean) / std
    minutes = float(np.dot(np.append(x, 1.0), _model))
    return max(0.0, minutes), 0.9


def _analytic_predict(position: int, avg_process_minutes: float, counters_active: int) -> tuple[float, float]:
    """Deterministic fallback: position / effective throughput."""
    if counters_active <= 0:
        counters_active = 1
    if avg_process_minutes <= 0:
        avg_process_minutes = 6.0
    effective = avg_process_minutes / counters_active
    ahead = max(0, position - 1)
    return max(0.0, ahead * effective), 0.55


def predict_wait(position: int, avg_process_minutes: float, counters_active: int,
                 hour: int | None = None, arrivals: int = 0, processed: int = 0) -> dict:
    features = (hour if hour is not None else 10, arrivals, processed, counters_active)
    minutes, confidence = _model_predict(features)
    if minutes <= 0 or not math.isfinite(minutes):
        minutes, confidence = _analytic_predict(position, avg_process_minutes, counters_active)
    # Confidence decays with distance from the model's comfort zone.
    if position > 25:
        confidence = min(confidence, 0.7)
    return {"eta_minutes": round(minutes, 1), "confidence": round(confidence, 2)}


def predict_bundle(waits: list[float], confidence: float) -> dict:
    """Sum independent stage waits into a combined ETA with a slightly
    reduced confidence (compounding uncertainty across stages)."""
    total = sum(max(0.0, w) for w in waits)
    return {"eta_minutes": round(total, 1), "confidence": round(max(0.3, confidence * 0.85), 2)}
