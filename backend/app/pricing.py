"""MSP pricing used by the quality-check stage (prototype constants)."""

MSP_PER_KG = {
    "Paddy": 23.0,
    "Wheat": 24.25,
    "Maize": 21.20,
}

GRADE_FACTOR = {"A": 1.0, "B": 0.92}


def procurement_amount(crop: str, grade: str, quantity_kg: float) -> float:
    base = MSP_PER_KG.get(crop, 20.0)
    factor = GRADE_FACTOR.get(grade, 1.0)
    return round(base * factor * quantity_kg, 2)
