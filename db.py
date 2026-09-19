"""SQLite storage. One connection per call keeps the threaded server simple."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

DB_PATH = os.environ.get("ONA_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ona.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    phone TEXT,
    district TEXT,
    due_date TEXT NOT NULL,
    risk_factors TEXT NOT NULL DEFAULT '[]',
    doctor TEXT,
    lang TEXT NOT NULL DEFAULT 'uz'
);
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    day TEXT NOT NULL,
    answers TEXT NOT NULL,
    level TEXT NOT NULL,
    reasons TEXT NOT NULL DEFAULT '[]',
    feedback TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(patient_id, day)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    source TEXT NOT NULL,
    level TEXT NOT NULL,
    reasons TEXT NOT NULL DEFAULT '[]',
    note TEXT,
    created_at TEXT NOT NULL,
    ack_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    channel TEXT NOT NULL,
    sender TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    patient_id INTEGER NOT NULL,
    lang TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (patient_id, lang)
);
"""
# messages.channel: 'ai' = mother <-> AI assistant, 'clinic' = mother <-> clinic staff
# messages.sender:  'patient' | 'ai' | 'clinic'


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with connect() as c:
        c.executescript(SCHEMA)
        # invite_token: the secret in the link / QR code a clinic gives to a mother (added after the first release)
        if "invite_token" not in [r["name"] for r in c.execute("PRAGMA table_info(patients)")]:
            c.execute("ALTER TABLE patients ADD COLUMN invite_token TEXT")
        for row in c.execute("SELECT id FROM patients WHERE invite_token IS NULL").fetchall():
            c.execute("UPDATE patients SET invite_token=? WHERE id=?", (secrets.token_urlsafe(9), row["id"]))


def now():
    return datetime.now().isoformat(timespec="seconds")


def week_of(due_date, on=None):
    on = on or date.today()
    days_left = (date.fromisoformat(due_date) - on).days
    return max(1, min(42, (280 - days_left) // 7))  # completed gestational weeks


def _patient(row):
    p = dict(row)
    p["risk_factors"] = json.loads(p["risk_factors"])
    p["week"] = week_of(p["due_date"])
    return p


def _checkin(row):
    c = dict(row)
    c["answers"] = json.loads(c["answers"])
    c["reasons"] = json.loads(c["reasons"])
    return c


def _alert(row):
    a = dict(row)
    a["reasons"] = json.loads(a["reasons"])
    return a


# ---- patients ---------------------------------------------------------------

def add_patient(**f):
    with connect() as c:
        cur = c.execute(
            "INSERT INTO patients (name, age, phone, district, due_date, risk_factors, doctor, lang, invite_token) VALUES (?,?,?,?,?,?,?,?,?)",
            (f["name"], f.get("age"), f.get("phone"), f.get("district"), f["due_date"],
             json.dumps(f.get("risk_factors", [])), f.get("doctor"), f.get("lang", "uz"), secrets.token_urlsafe(9)),
        )
        return cur.lastrowid


def patient_by_token(token):
    with connect() as c:
        row = c.execute("SELECT * FROM patients WHERE invite_token=?", (token or "",)).fetchone()
    return _patient(row) if row else None


def get_patient(pid):
    with connect() as c:
        row = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    return _patient(row) if row else None


def list_patients():
    with connect() as c:
        return [_patient(r) for r in c.execute("SELECT * FROM patients ORDER BY name")]


# ---- check-ins --------------------------------------------------------------

def save_checkin(pid, day, answers, level, reasons, feedback=None, created_at=None):
    with connect() as c:
        c.execute(
            "INSERT INTO checkins (patient_id, day, answers, level, reasons, feedback, created_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(patient_id, day) DO UPDATE SET answers=excluded.answers, level=excluded.level, "
            "reasons=excluded.reasons, feedback=excluded.feedback, created_at=excluded.created_at",
            (pid, day, json.dumps(answers, ensure_ascii=False), level, json.dumps(reasons), feedback, created_at or now()),
        )
        c.execute("DELETE FROM summaries WHERE patient_id=?", (pid,))
        return c.execute("SELECT id FROM checkins WHERE patient_id=? AND day=?", (pid, day)).fetchone()["id"]


def checkins(pid, limit=30, before=None):
    q, args = "SELECT * FROM checkins WHERE patient_id=?", [pid]
    if before:
        q += " AND day<?"
        args.append(before)
    with connect() as c:
        rows = c.execute(q + " ORDER BY day DESC LIMIT ?", args + [limit]).fetchall()
    return [_checkin(r) for r in rows]


# ---- alerts -----------------------------------------------------------------

def add_alert(pid, source, level, reasons, note=None, created_at=None):
    with connect() as c:
        # one open alert per patient per source per day is enough; refresh it instead of stacking
        c.execute("DELETE FROM alerts WHERE patient_id=? AND source=? AND ack_at IS NULL AND substr(created_at,1,10)=?",
                  (pid, source, date.today().isoformat()))
        return c.execute(
            "INSERT INTO alerts (patient_id, source, level, reasons, note, created_at) VALUES (?,?,?,?,?,?)",
            (pid, source, level, json.dumps(reasons), note, created_at or now()),
        ).lastrowid


def clear_open_alerts(pid, source):
    with connect() as c:
        c.execute("DELETE FROM alerts WHERE patient_id=? AND source=? AND ack_at IS NULL", (pid, source))


def open_alerts(pid=None):
    q = "SELECT a.*, p.name AS patient_name FROM alerts a JOIN patients p ON p.id=a.patient_id WHERE a.ack_at IS NULL"
    args = []
    if pid:
        q += " AND a.patient_id=?"
        args.append(pid)
    with connect() as c:
        rows = c.execute(q + " ORDER BY (a.level='red') DESC, a.created_at DESC", args).fetchall()
    return [_alert(r) for r in rows]


def ack_alert(aid):
    with connect() as c:
        c.execute("UPDATE alerts SET ack_at=? WHERE id=?", (now(), aid))


# ---- messages ---------------------------------------------------------------

def add_message(pid, channel, sender, text, created_at=None):
    with connect() as c:
        return c.execute(
            "INSERT INTO messages (patient_id, channel, sender, text, created_at) VALUES (?,?,?,?,?)",
            (pid, channel, sender, text, created_at or now()),
        ).lastrowid


def messages(pid, channel, limit=40):
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM (SELECT * FROM messages WHERE patient_id=? AND channel=? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (pid, channel, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- clinic staff accounts --------------------------------------------------

def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200000).hex()


def add_user(username, name, role, password):
    salt = secrets.token_hex(16)
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO users (username, name, role, salt, password_hash) VALUES (?,?,?,?,?)",
                  (username.lower(), name, role, salt, _hash(password, salt)))


def login(username, password):
    """Returns (token, user) or None. The hash is computed even for unknown users to keep timing flat."""
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),)).fetchone()
        digest = _hash(password or "", row["salt"] if row else "00" * 16)
        if not row or not hmac.compare_digest(digest, row["password_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions (token, username, created_at) VALUES (?,?,?)", (token, row["username"], now()))
        return token, {"username": row["username"], "name": row["name"], "role": row["role"]}


def session_user(token):
    if not token:
        return None
    with connect() as c:
        row = c.execute("SELECT u.username, u.name, u.role FROM sessions s JOIN users u ON u.username=s.username WHERE s.token=?",
                        (token,)).fetchone()
    return dict(row) if row else None


def logout(token):
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ---- cached AI summaries ----------------------------------------------------

def get_summary(pid, lang):
    with connect() as c:
        row = c.execute("SELECT body, created_at FROM summaries WHERE patient_id=? AND lang=?", (pid, lang)).fetchone()
    return dict(json.loads(row["body"]), created_at=row["created_at"]) if row else None


def put_summary(pid, lang, body):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO summaries (patient_id, lang, body, created_at) VALUES (?,?,?,?)",
                  (pid, lang, json.dumps(body, ensure_ascii=False), now()))


def days_since(day):
    return (date.today() - date.fromisoformat(day)).days


def day_offset(n):
    return (date.today() - timedelta(days=n)).isoformat()
