import sqlite3
import threading
import time
from datetime import datetime

from .config import settings

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS mandis (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    district  TEXT NOT NULL,
    lat       REAL NOT NULL,
    lng       REAL NOT NULL,
    opens_at  TEXT NOT NULL DEFAULT '08:00',
    closes_at TEXT NOT NULL DEFAULT '17:00'
);

CREATE TABLE IF NOT EXISTS counters (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    mandi_id          TEXT NOT NULL REFERENCES mandis(id),
    code              TEXT NOT NULL,
    type              TEXT NOT NULL CHECK (type IN ('WEIGHING', 'QUALITY_CHECK')),
    current_ticket_id INTEGER,
    sim_next_minutes  INTEGER,
    is_active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tickets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    token               TEXT UNIQUE NOT NULL,
    mandi_id            TEXT NOT NULL REFERENCES mandis(id),
    phone               TEXT NOT NULL,
    farmer_name         TEXT NOT NULL,
    crop                TEXT NOT NULL,
    quantity_kg         REAL NOT NULL,
    slot_date           TEXT NOT NULL,
    slot_time           TEXT NOT NULL,
    lang                TEXT NOT NULL DEFAULT 'ml',
    status              TEXT NOT NULL DEFAULT 'SLOT_BOOKED'
                        CHECK (status IN ('SLOT_BOOKED','ARRIVED','WEIGHING','QUALITY_CHECK','PAYMENT','COMPLETED','NO_SHOW','CANCELLED')),
    position            INTEGER,
    eta_minutes         REAL,
    priority            INTEGER NOT NULL DEFAULT 0,
    priority_flag       TEXT,
    dispute_count       INTEGER NOT NULL DEFAULT 0,
    last_eta_minutes    REAL,
    prev_eta_minutes    REAL,
    no_show_risk        REAL,
    risk_band           TEXT,
    escalated           INTEGER NOT NULL DEFAULT 0,
    alert_ack_at        TEXT,
    stage_started_at    TEXT,
    quality_grade       TEXT,
    amount              REAL,
    payment_status      TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (payment_status IN ('PENDING','PROCESSING','COMPLETED','DELAYED')),
    payment_submitted_at TEXT,
    payment_completed_at TEXT,
    payment_delayed     INTEGER NOT NULL DEFAULT 0,
    leave_home_alerted  INTEGER NOT NULL DEFAULT 0,
    turn_soon_alerted   INTEGER NOT NULL DEFAULT 0,
    checked_in_at       TEXT,
    no_shown_at         TEXT,
    completed_at        TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_mandi_status ON tickets(mandi_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_phone ON tickets(phone, slot_date);
CREATE INDEX IF NOT EXISTS idx_tickets_slot ON tickets(slot_date, slot_time);

CREATE TABLE IF NOT EXISTS audit_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    mandi_id  TEXT,
    ticket_id INTEGER,
    actor     TEXT NOT NULL,
    action    TEXT NOT NULL,
    details   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit_events(ticket_id);

CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id    INTEGER,
    phone        TEXT NOT NULL,
    channel      TEXT NOT NULL,
    template_key TEXT NOT NULL,
    lang         TEXT NOT NULL,
    body         TEXT NOT NULL,
    simulated    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS staff_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('STAFF', 'ADMIN')),
    mandi_id      TEXT,
    name          TEXT
);

CREATE TABLE IF NOT EXISTS farmers (
    phone      TEXT PRIMARY KEY,
    mm_id      TEXT UNIQUE NOT NULL,
    name       TEXT,
    lang       TEXT NOT NULL DEFAULT 'ml',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER UNIQUE NOT NULL,
    token      TEXT NOT NULL,
    mandi_id   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mandi_status (
    mandi_id   TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'OPEN'
               CHECK (status IN ('OPEN','CLOSED','TEMP_CLOSED','PAUSED','HIGH_CONGESTION','PAYMENT_DELAY','WEATHER')),
    note       TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token      TEXT NOT NULL,
    phone      TEXT NOT NULL,
    mandi_id   TEXT NOT NULL,
    waiting    INTEGER NOT NULL,
    staff      INTEGER NOT NULL,
    queue_mgmt INTEGER NOT NULL,
    info       INTEGER NOT NULL,
    payment    INTEGER NOT NULL,
    facilities INTEGER NOT NULL,
    overall    INTEGER NOT NULL,
    comment    TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grievances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    grievance_id TEXT UNIQUE NOT NULL,
    token       TEXT,
    phone       TEXT NOT NULL,
    mandi_id    TEXT NOT NULL,
    category    TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'SUBMITTED'
                CHECK (status IN ('SUBMITTED','ASSIGNED','UNDER_REVIEW','ACTION_TAKEN','RESOLVED')),
    assigned_to TEXT,
    resolution  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_docs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT NOT NULL,
    source  TEXT NOT NULL,
    updated TEXT NOT NULL,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history_stats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    mandi_id       TEXT NOT NULL,
    date           TEXT NOT NULL,
    hour           INTEGER NOT NULL,
    arrivals       INTEGER NOT NULL,
    processed      INTEGER NOT NULL,
    avg_wait_min   REAL NOT NULL,
    counters_active INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history ON history_stats(mandi_id, date);
"""


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        _local.conn = conn
    return conn


def query(sql: str, params=()):
    return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params=()):
    return get_conn().execute(sql, params).fetchone()


_write_lock = threading.Lock()


def execute(sql: str, params=()):
    """Serialized write with retry — SQLite allows one writer at a time."""
    conn = get_conn()
    for attempt in range(5):
        try:
            with _write_lock:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 4:
                time.sleep(0.15 * (attempt + 1))
            else:
                raise


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Lightweight migrations for databases created before newer columns.
    for stmt in (
        "ALTER TABLE tickets ADD COLUMN priority_flag TEXT",
        "ALTER TABLE tickets ADD COLUMN dispute_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE tickets ADD COLUMN last_eta_minutes REAL",
        "ALTER TABLE tickets ADD COLUMN prev_eta_minutes REAL",
        "ALTER TABLE tickets ADD COLUMN no_show_risk REAL",
        "ALTER TABLE tickets ADD COLUMN risk_band TEXT",
        "ALTER TABLE tickets ADD COLUMN escalated INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE tickets ADD COLUMN alert_ack_at TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()
