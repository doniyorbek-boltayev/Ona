"""Synthetic demo data: 10 patients of a private clinic in Urgench with 14 days of check-ins.

Every check-in goes through the real triage engine, so the dashboard shows what the
rules actually produce. Patient 1 (Dilnoza) has no check-in for today: she is the
persona used in the mother app during the live demo.

    python seed.py --reset
"""
import os
import random
import sys
from datetime import date, timedelta

import ai
import db
import triage

DAYS = 14
CLINIC = {"name": "Xorazm Nigoh Klinikasi", "city": "Urganch", "phone": "+998 62 000 00 00"}


def _base(rng, weight, day_index, gain_per_week=0.4):
    return {
        "mood": rng.choice([3, 4, 4, 4, 5]),
        "symptoms": ["none"],
        "movement": "normal",
        "bp": {"sys": rng.randint(108, 122), "dia": rng.randint(68, 78)},
        "weight": round(weight + gain_per_week * day_index / 7.0 + rng.uniform(-0.2, 0.2), 1),
        "sleep": rng.choice(["5to7", "gt7", "gt7"]),
        "anxiety": rng.choice([1, 2, 2, 3]),
        "meds": "yes" if rng.random() > 0.1 else "no",
        "note": "",
    }


# Each scenario mutates the healthy baseline. i = 0 (oldest) .. 13 (today); return None to skip the day.

def healthy(a, i, rng):
    if i == 9:
        a.update(symptoms=["dizziness"], note="Ertalab biroz boshim aylandi, keyin o'tib ketdi.")
    return a


def rising_bp(a, i, rng):
    a["bp"] = {"sys": 124 + i * 2 + rng.randint(-2, 2), "dia": 80 + i + rng.randint(-1, 2)}
    if i >= 10:
        a.update(symptoms=["headache"], headache_severity="moderate", mood=3)
    if i >= 12:
        a.update(symptoms=["headache", "swelling"], headache_severity="severe", anxiety=4, mood=2,
                 note="Boshim qattiq og'riyapti, qo'llarim shishgan. Uzugim sig'may qoldi.")
    if i == 13:
        a["symptoms"].append("vision")
        a["bp"] = {"sys": 152, "dia": 98}
    return a


def reduced_movement(a, i, rng):
    if i == 13:
        a.update(movement="less", anxiety=4, note="Bugun bolam odatdagidan kam qimirladi, xavotirdaman.")
    return a


def weight_jump(a, i, rng):
    if i >= 10:
        a["weight"] = round(a["weight"] + (i - 9) * 0.8, 1)
    if i >= 12:
        a["symptoms"] = ["swelling"]
    return a


def low_mood(a, i, rng):
    a.pop("movement")  # week 16: question not shown yet
    if i >= 8:
        a.update(mood=2, anxiety=rng.choice([4, 5]), sleep="lt5")
    if i == 12:
        a["note"] = "Erim ishga Rossiyaga ketgan, o'zimni yolg'iz his qilyapman. Tunda uxlay olmayapman."
    return a


def silent(a, i, rng):
    return a if i < 9 else None  # stopped answering five days ago


def nausea(a, i, rng):
    a.pop("movement")
    if i >= 7:
        a.update(symptoms=["vomiting"], mood=2 if i >= 11 else 3, meds="no",
                 note="Hech narsa yeya olmayapman, vitaminni ham qaytarib yuboryapman." if i == 13 else "")
    return a


def term_ready(a, i, rng):
    if i == 13:
        a.update(symptoms=["contractions"], note="To'lg'oq boshlandi shekilli, har 10 daqiqada.")
    return a


def gdm(a, i, rng):
    a["note"] = "Qand 5.4 (och qoringa)" if i % 4 == 0 else ""
    return a


PATIENTS = [
    # name, age, district, week today, risk factors, scenario, start weight, skip_today
    ("Dilnoza Karimova", 27, "Urganch", 31, ["mild anemia"], healthy, 68.0, True),
    ("Gulnora Rahimova", 34, "Xiva", 33, ["chronic hypertension", "BMI 31"], rising_bp, 82.0, False),
    ("Malika Yusupova", 22, "Hazorasp", 29, ["first pregnancy"], reduced_movement, 61.0, False),
    ("Sevara Otajonova", 30, "Shovot", 34, ["gestational diabetes"], weight_jump, 77.0, False),
    ("Nigora Sobirova", 25, "Gurlan", 16, ["husband working abroad"], low_mood, 58.0, False),
    ("Feruza Jumaniyozova", 38, "Xonqa", 26, ["age over 35", "previous caesarean"], silent, 70.0, False),
    ("Shahnoza Qurbonova", 24, "Bog'ot", 12, [], nausea, 55.0, False),
    ("Zilola Matyoqubova", 29, "Yangiariq", 39, [], term_ready, 74.0, False),
    ("Mohira Ismoilova", 31, "Urganch", 28, ["gestational diabetes"], gdm, 72.0, False),
    ("Kamola Bekchanova", 26, "Qo'shko'pir", 21, [], lambda a, i, rng: a, 60.0, False),
]

DOCTORS = ["Dr. Matkarimova", "Dr. Sultonova"]
# Clinic staff logins. One shared demo password, overridable for a public deployment.
STAFF = [("matkarimova", DOCTORS[0], "doctor"), ("sultonova", DOCTORS[1], "doctor"), ("admin", "Clinic admin", "admin")]
STAFF_PASSWORD = os.environ.get("ONA_CLINIC_PASSWORD", "ona2026")


def seed():
    rng = random.Random(7)
    today = date.today()
    for n, (name, age, district, week, risks, scenario, weight, skip_today) in enumerate(PATIENTS):
        due = today + timedelta(days=280 - week * 7 - 3)
        pid = db.add_patient(name=name, age=age, district=district, due_date=due.isoformat(), risk_factors=risks,
                             doctor=DOCTORS[n % 2], phone="+998 9%d %03d %02d %02d" % (rng.randint(0, 9), rng.randint(100, 999), rng.randint(10, 99), rng.randint(10, 99)))
        patient = db.get_patient(pid)
        history = []
        for i in range(DAYS):
            day = today - timedelta(days=DAYS - 1 - i)
            if i == DAYS - 1 and skip_today:
                continue
            if scenario is healthy and i in (3, 8):  # nobody answers every single day
                continue
            answers = scenario(_base(rng, weight, i), i, rng)
            if answers is None:
                continue
            result = triage.assess(answers, db.week_of(patient["due_date"], day), history)
            stamp = "%sT%02d:%02d:00" % (day.isoformat(), rng.randint(7, 10), rng.randint(0, 59))
            feedback = ai._feedback_template(patient, answers, result, "uz")
            db.save_checkin(pid, day.isoformat(), answers, result["level"], result["reasons"], feedback, created_at=stamp)
            if result["level"] != triage.GREEN and i >= DAYS - 1:
                db.add_alert(pid, "checkin", result["level"], result["reasons"], note=answers.get("note") or None, created_at=stamp)
            history.insert(0, answers)

    yesterday = (today - timedelta(days=1)).isoformat()
    db.add_message(1, "clinic", "clinic", "Assalomu alaykum, Dilnoza! Gemoglobin tahlilingiz yaxshilanibdi (108 g/l). Temir preparatini davom ettiring.", created_at=yesterday + "T15:20:00")
    db.add_message(1, "clinic", "patient", "Rahmat, doktor! Keyingi ko'rik qachon?", created_at=yesterday + "T15:42:00")
    db.add_message(1, "clinic", "clinic", "Kelasi seshanba, soat 10:00 da kutamiz.", created_at=yesterday + "T16:05:00")
    db.add_alert(5, "chat", "yellow", [], note="Patient says she cries at night and feels alone since her husband left for work abroad.",
                 created_at=yesterday + "T22:14:00")


def ensure_staff():
    for username, name, role in STAFF:
        db.add_user(username, name, role, STAFF_PASSWORD)


def reset():
    db.init()
    with db.connect() as c:  # keep users and sessions so a reset on stage does not log the clinic out
        for table in ("summaries", "messages", "alerts", "checkins", "patients"):
            c.execute("DELETE FROM %s" % table)
    ensure_staff()
    seed()


if __name__ == "__main__":
    if "--reset" in sys.argv or not os.path.exists(db.DB_PATH):
        reset()
        print("Seeded %d patients into %s" % (len(db.list_patients()), db.DB_PATH))
    else:
        print("Database exists. Use --reset to regenerate.")
