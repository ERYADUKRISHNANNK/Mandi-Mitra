"""Procurement rates with explicit source stamping.

IMPORTANT PROTOTYPE NOTE: values are the MSP constants already used by the
procurement engine. A production deployment must bind these to the official
government rate feed; the UI always shows the source + updated timestamp so
farmers are never shown an unofficial number presented as official.
"""

from .db import now_iso

SOURCE = "Prototype MSP reference (deployment: bind to official govt rate feed)"
UPDATED = None  # computed per call

RATE_PER_QUINTAL = {
    "Paddy": 2300.0,   # ₹ per quintal (common man-friendly unit)
    "Wheat": 2425.0,
    "Maize": 2120.0,
}


def rate_for(crop: str) -> dict:
    per_q = RATE_PER_QUINTAL.get(crop)
    return {
        "crop": crop,
        "rate_per_quintal": per_q,
        "source": SOURCE,
        "updated_at": now_iso(),
        "procurement_open": per_q is not None,
    }


def estimated_value(crop: str, quantity_kg: float) -> float | None:
    per_q = RATE_PER_QUINTAL.get(crop)
    if per_q is None:
        return None
    return round(per_q * quantity_kg / 100.0, 2)
