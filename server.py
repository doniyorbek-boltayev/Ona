"""Ona demo server: JSON API + static files, Python standard library only.

    python server.py [port]

Demo only: clinic staff sign in, the mother app does not, and all patient data is synthetic.
"""
import json
import mimetypes
import time
import os
import re
import socket
import sys
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import ai
import db
import questions
import seed
import triage

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
PAGES = {"/": "app/index.html", "/clinic": "clinic/index.html", "/demo": "demo.html"}
SILENT_AFTER_DAYS = 3
SESSION_COOKIE = "ona_session"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _lang(value):
    return value if value in questions.LANGS else "uz"


def _need_patient(pid):
    patient = db.get_patient(pid)
    if not patient:
        raise ApiError(404, "patient not found")
    return patient


# ---- API handlers -----------------------------------------------------------

def api_status(_req):
    return {"ai": ai.status(), "clinic": seed.CLINIC, "today": date.today().isoformat()}


def api_questions(_req):
    return {"langs": questions.LANGS, "questions": questions.QUESTIONS,
            "reasons": {code: {"level": lvl, "text": text} for code, (lvl, text) in triage.REASONS.items()},
            "symptoms": {s["id"]: s["label"] for s in questions.SYMPTOMS}}


def _patient_row(patient):
    history = db.checkins(patient["id"], limit=14)
    last = history[0] if history else None
    silent_days = db.days_since(last["day"]) if last else None
    alerts = db.open_alerts(patient["id"])
    level = last["level"] if last and silent_days <= 1 else triage.GREEN
    if alerts:
        level = triage.worst(level, *[a["level"] for a in alerts])
    by_day = {c["day"]: c["level"] for c in history}
    return dict(patient, level=level, open_alerts=len(alerts),
                silent=silent_days is None or silent_days >= SILENT_AFTER_DAYS, silent_days=silent_days,
                last_checkin=last and {"day": last["day"], "level": last["level"], "reasons": last["reasons"], "created_at": last["created_at"]},
                timeline=[by_day.get(db.day_offset(n)) for n in range(13, -1, -1)])


def api_patients(_req):
    rows = [_patient_row(p) for p in db.list_patients()]
    rows.sort(key=lambda r: (-triage.ORDER[r["level"]], not r["silent"], r["name"]))
    return {"patients": rows, "alerts": db.open_alerts()}


def api_patient(req):
    patient = _need_patient(req["id"])
    history = db.checkins(patient["id"], limit=30)
    today = date.today().isoformat()
    streak = 0
    expected = db.days_since(history[0]["day"]) if history else 0  # a streak may end today or yesterday
    for c in history if expected <= 1 else []:
        if db.days_since(c["day"]) != expected:
            break
        streak, expected = streak + 1, expected + 1
    return {"patient": _patient_row(patient), "checkins": history, "streak": streak,
            "today": next((c for c in history if c["day"] == today), None),
            "alerts": db.open_alerts(patient["id"]),
            "clinic_messages": db.messages(patient["id"], "clinic"),
            "ai_messages": db.messages(patient["id"], "ai"),
            "summary": db.get_summary(patient["id"], _lang(req["query"].get("lang"))),
            "clinic": seed.CLINIC}


def api_checkin(req):
    body = req["body"]
    patient = _need_patient(body.get("patient_id"))
    answers, lang = body.get("answers"), _lang(body.get("lang"))
    if not isinstance(answers, dict) or "mood" not in answers:
        raise ApiError(400, "answers are required")
    today = date.today().isoformat()
    history = [c["answers"] for c in db.checkins(patient["id"], limit=7, before=today)]
    result = triage.assess(answers, patient["week"], history)
    feedback = ai.checkin_feedback(patient, answers, result, lang)
    db.save_checkin(patient["id"], today, answers, result["level"], result["reasons"], feedback["text"])
    if result["level"] == triage.GREEN:
        db.clear_open_alerts(patient["id"], "checkin")
    else:
        db.add_alert(patient["id"], "checkin", result["level"], result["reasons"], note=(answers.get("note") or "").strip() or None)
    return dict(result, feedback=feedback["text"], source=feedback["source"])


def api_chat(req):
    body = req["body"]
    patient = _need_patient(body.get("patient_id"))
    text = (body.get("text") or "").strip()[:2000]
    if not text:
        raise ApiError(400, "text is required")
    db.add_message(patient["id"], "ai", "patient", text)
    out = ai.chat(patient, db.messages(patient["id"], "ai"), db.checkins(patient["id"], limit=5), _lang(body.get("lang")))
    db.add_message(patient["id"], "ai", "ai", out["reply"])
    if out["escalate"] != "none":
        level = triage.RED if out["escalate"] == "urgent" else triage.YELLOW
        db.add_alert(patient["id"], "chat", level, [], note="%s Patient wrote: %s" % (out["escalate_reason"], text[:200]))
    return {"reply": out["reply"], "escalate": out["escalate"], "source": out["source"]}


def api_summary(req):
    patient = _need_patient(req["id"])
    lang = _lang(req["body"].get("lang"))
    cached = None if req["body"].get("refresh") else db.get_summary(patient["id"], lang)
    if cached:
        return cached
    body = ai.clinical_summary(patient, db.checkins(patient["id"], limit=14), lang)
    db.put_summary(patient["id"], lang, body)
    return db.get_summary(patient["id"], lang)


def api_message(req):
    patient = _need_patient(req["id"])
    text = (req["body"].get("text") or "").strip()[:2000]
    sender = req["body"].get("sender")
    if not text or sender not in ("clinic", "patient"):
        raise ApiError(400, "text and sender (clinic|patient) are required")
    if sender == "clinic" and not req["user"]:
        raise ApiError(401, "login required")
    db.add_message(patient["id"], "clinic", sender, text)
    return {"messages": db.messages(patient["id"], "clinic")}


def api_ack(req):
    db.ack_alert(req["id"])
    return {"ok": True}


def api_login(req):
    session = db.login(req["body"].get("username"), req["body"].get("password"))
    if not session:
        time.sleep(0.7)  # slow down password guessing
        raise ApiError(401, "wrong username or password")
    token, user = session
    req["set_cookie"] = "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200" % (SESSION_COOKIE, token)
    return {"user": user}


def api_logout(req):
    db.logout(req["token"])
    req["set_cookie"] = "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" % SESSION_COOKIE
    return {"ok": True}


def api_me(req):
    return {"user": req["user"]}


def api_personas(_req):
    """Names for the stage view's phone switcher; open because the stage view has no login of its own."""
    return {"personas": [{"id": p["id"], "name": p["name"], "week": p["week"]} for p in sorted(db.list_patients(), key=lambda p: p["id"])]}


def api_reset(_req):
    seed.reset()
    return {"ok": True}


# (method, path, handler, clinic staff only). The mother app has no login in this demo, so the
# endpoints it uses stay open; everything only the dashboard needs requires a staff session.
ROUTES = [
    ("GET", r"/api/status", api_status, False),
    ("GET", r"/api/questions", api_questions, False),
    ("POST", r"/api/login", api_login, False),
    ("POST", r"/api/logout", api_logout, False),
    ("GET", r"/api/me", api_me, True),
    ("GET", r"/api/patients", api_patients, True),
    ("GET", r"/api/patients/(\d+)", api_patient, False),
    ("POST", r"/api/checkins", api_checkin, False),
    ("POST", r"/api/chat", api_chat, False),
    ("POST", r"/api/patients/(\d+)/summary", api_summary, True),
    ("POST", r"/api/patients/(\d+)/messages", api_message, False),
    ("POST", r"/api/alerts/(\d+)/ack", api_ack, True),
    ("POST", r"/api/demo/reset", api_reset, False),
    ("GET", r"/api/demo/personas", api_personas, False),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "Ona/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in self.path and self.command == "GET":
            return  # dashboard polling would flood the console
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, status, payload, content_type="application/json; charset=utf-8", cookie=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method):
        url = urlparse(self.path)
        for verb, pattern, handler, staff_only in ROUTES:
            match = re.fullmatch(pattern, url.path.rstrip("/"))
            if not match or verb != method:
                continue
            body = {}
            if method == "POST":
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    return self._send(400, {"error": "invalid JSON"})
            try:
                morsel = SimpleCookie(self.headers.get("Cookie") or "").get(SESSION_COOKIE)
            except Exception:  # a malformed Cookie header just means "not logged in"
                morsel = None
            token = morsel.value if morsel else None
            req = {"id": int(match.group(1)) if match.groups() else None, "body": body,
                   "query": {k: v[0] for k, v in parse_qs(url.query).items()},
                   "token": token, "user": db.session_user(token)}
            if staff_only and not req["user"]:
                return self._send(401, {"error": "login required"})
            try:
                payload = handler(req)
                return self._send(200, payload, cookie=req.get("set_cookie"))
            except ApiError as e:
                return self._send(e.status, {"error": str(e)})
            except Exception as e:  # keep the demo alive and show what broke
                sys.stderr.write("ERROR %s %s: %r\n" % (method, url.path, e))
                return self._send(500, {"error": "internal error: %s" % e})
        self._send(404, {"error": "not found"})

    def _static(self):
        path = urlparse(self.path).path
        rel = PAGES.get(path.rstrip("/") or "/")
        if rel is None and path.startswith("/static/"):
            rel = path[len("/static/"):]
        full = os.path.realpath(os.path.join(STATIC, rel)) if rel else None
        if not full or not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self._send(404, b"Not found", "text/plain")
        with open(full, "rb") as f:
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "application/manifest+json"):
                ctype += "; charset=utf-8"
            self._send(200, f.read(), ctype)

    def do_GET(self):
        self._api("GET") if self.path.startswith("/api/") else self._static()

    def do_POST(self):
        self._api("POST") if self.path.startswith("/api/") else self._send(404, {"error": "not found"})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    mimetypes.add_type("font/woff2", ".woff2")
    fresh = not os.path.exists(db.DB_PATH)
    db.init()
    if fresh or not db.list_patients():
        seed.reset()
    seed.ensure_staff()
    status = ai.status()
    print("Ona is running")
    print("  Mother app : http://localhost:%d/" % port)
    print("  Clinic     : http://localhost:%d/clinic" % port)
    print("  Stage view : http://localhost:%d/demo" % port)
    print("  Clinic login: %s / %s" % (seed.STAFF[0][0], seed.STAFF_PASSWORD))
    print("  On a phone : http://%s:%d/  (same Wi-Fi)" % (lan_ip(), port))
    print("  AI mode    : %s" % ("%s (%s)" % (status["provider"], status["model"]) if status["mode"] == "live" else "offline templates — put an API key in .env for live AI"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
