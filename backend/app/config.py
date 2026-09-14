import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)


class Settings:
    db_path = os.environ.get("MM_DB_PATH", os.path.join(BACKEND_DIR, "mandi_mitra.db"))
    jwt_secret = os.environ.get("MM_JWT_SECRET", "mandi-mitra-dev-secret-change-in-production")
    jwt_algorithm = "HS256"
    token_expiry_minutes = 12 * 60

    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    # --- Domain tuning ---------------------------------------------------
    # A payment stuck in PROCESSING longer than this is flagged (prototype
    # uses minutes so the demo can show it; production would use 48-72h).
    payment_delay_minutes = 10
    # Fire "leave home" when the farmer's ETA drops below this many minutes.
    leave_home_lead_minutes = 45
    # Turn-approaching alert when this many farmers remain ahead.
    turn_soon_position = 2
    # A stage taking longer than this on a counter is flagged as slow.
    slow_stage_minutes = 25
    # Booking velocity alert threshold (bookings per hour per phone).
    booking_velocity_limit = 4


settings = Settings()
