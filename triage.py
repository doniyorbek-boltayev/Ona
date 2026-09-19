"""Deterministic risk engine for daily check-ins.

Rules follow the WHO antenatal-care danger signs. This module is the single source
of truth for the risk level: AI features may explain a level but never lower it.

assess(answers, week, history) -> {"level": "green"|"yellow"|"red", "reasons": [code, ...]}
`history` is a list of previous check-in answer dicts, newest first.
"""

GREEN, YELLOW, RED = "green", "yellow", "red"
ORDER = {GREEN: 0, YELLOW: 1, RED: 2}


def _t(uz, ru, en):
    return {"uz": uz, "ru": ru, "en": en}


# code -> (level, localized explanation for clinicians and for the mother's result screen)
REASONS = {
    "bleeding": (RED, _t("Qon ketishi", "Кровянистые выделения", "Vaginal bleeding")),
    "fluid_leak": (RED, _t("Suv ketishi ehtimoli", "Возможное подтекание вод", "Possible leaking of amniotic fluid")),
    "no_movement": (RED, _t("Bola harakati sezilmagan", "Нет шевелений плода", "No fetal movement felt")),
    "bp_severe": (RED, _t("Qon bosimi juda yuqori (≥160/110)", "Очень высокое давление (≥160/110)", "Severely high blood pressure (≥160/110)")),
    "preeclampsia_signs": (RED, _t("Preeklampsiya belgilari (bosh og'rig'i, ko'rish, shish, bosim)", "Признаки преэклампсии (головная боль, зрение, отёки, давление)", "Pre-eclampsia warning signs (headache, vision, swelling, BP)")),
    "abdominal_pain": (RED, _t("Qorinda kuchli og'riq", "Сильная боль в животе", "Severe abdominal pain")),
    "preterm_contractions": (RED, _t("37 haftagacha muntazam to'lg'oqlar", "Регулярные схватки до 37 недель", "Regular contractions before 37 weeks")),
    "breathless": (RED, _t("Nafas olish qiyinlashgan", "Затруднённое дыхание", "Difficulty breathing")),
    "fever_with_pain": (RED, _t("Isitma va og'riq birga", "Температура в сочетании с болью", "Fever together with pain")),
    "bp_high": (YELLOW, _t("Qon bosimi yuqori (≥140/90)", "Повышенное давление (≥140/90)", "High blood pressure (≥140/90)")),
    "less_movement": (YELLOW, _t("Bola harakati kamaygan", "Шевелений меньше обычного", "Reduced fetal movement")),
    "severe_headache": (YELLOW, _t("Kuchli bosh og'rig'i", "Сильная головная боль", "Severe headache")),
    "vision": (YELLOW, _t("Ko'rishdagi o'zgarishlar", "Нарушения зрения", "Visual disturbance")),
    "swelling": (YELLOW, _t("Yuz yoki qo'llar shishi", "Отёк лица или рук", "Swelling of face or hands")),
    "fever": (YELLOW, _t("Isitma", "Повышенная температура", "Fever")),
    "vomiting": (YELLOW, _t("To'xtovsiz qusish", "Многократная рвота", "Persistent vomiting")),
    "dizziness": (YELLOW, _t("Bosh aylanishi", "Головокружение", "Dizziness")),
    "urination": (YELLOW, _t("Siydik yo'li infeksiyasi belgilari", "Признаки инфекции мочевых путей", "Signs of urinary infection")),
    "term_contractions": (YELLOW, _t("Muntazam to'lg'oqlar — tug'ruq boshlanishi mumkin", "Регулярные схватки — возможно начало родов", "Regular contractions — labour may be starting")),
    "rapid_weight_gain": (YELLOW, _t("Bir haftada 2 kg dan ortiq vazn qo'shilgan", "Прибавка более 2 кг за неделю", "More than 2 kg gained in a week")),
    "low_mood_streak": (YELLOW, _t("3 kun ketma-ket kayfiyat past", "Сниженное настроение 3 дня подряд", "Low mood three days in a row")),
    "anxiety_streak": (YELLOW, _t("3 kun ketma-ket kuchli xavotir", "Сильная тревога 3 дня подряд", "High anxiety three days in a row")),
    "missed_meds_streak": (YELLOW, _t("3 kun vitamin/temir ichilmagan", "3 дня без витаминов/железа", "Supplements missed three days in a row")),
}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bp(answers):
    bp = answers.get("bp") or {}
    sys, dia = _num(bp.get("sys")), _num(bp.get("dia"))
    # ignore physiologically impossible typing mistakes rather than raise a false alarm
    if sys is None or dia is None or not (60 <= sys <= 260) or not (30 <= dia <= 160):
        return None, None
    return sys, dia


def _streak(answers, history, predicate, days=3):
    recent = [answers] + list(history[: days - 1])
    return len(recent) == days and all(predicate(a) for a in recent)


def assess(answers, week, history=()):
    symptoms = set(answers.get("symptoms") or []) - {"none"}
    sys, dia = _bp(answers)
    reasons = []

    def add(code):
        if code not in reasons:
            reasons.append(code)

    for code in ("bleeding", "fluid_leak", "abdominal_pain", "breathless"):
        if code in symptoms:
            add(code)

    if week >= 24:
        if answers.get("movement") == "none":
            add("no_movement")
        elif answers.get("movement") == "less":
            add("less_movement")

    if "contractions" in symptoms:
        add("preterm_contractions" if week < 37 else "term_contractions")

    bp_high = sys is not None and (sys >= 140 or dia >= 90)
    if sys is not None and (sys >= 160 or dia >= 110):
        add("bp_severe")
    elif bp_high:
        add("bp_high")

    severe_headache = "headache" in symptoms and answers.get("headache_severity") == "severe"
    neuro = [severe_headache, "vision" in symptoms, "swelling" in symptoms]
    # pre-eclampsia: raised BP with any warning symptom, or two warning symptoms together (week 20+)
    if week >= 20 and ((bp_high and any(neuro)) or sum(neuro) >= 2):
        add("preeclampsia_signs")
    if severe_headache:
        add("severe_headache")
    for code in ("vision", "swelling", "vomiting", "dizziness", "urination"):
        if code in symptoms:
            add(code)

    if "fever" in symptoms:
        add("fever_with_pain" if symptoms & {"abdominal_pain", "urination"} else "fever")

    weight = _num(answers.get("weight"))
    if weight is not None:
        week_ago = [_num(h.get("weight")) for h in history[:7]]
        week_ago = [w for w in week_ago if w is not None]
        if week_ago and weight - min(week_ago) > 2:
            add("rapid_weight_gain")

    if _streak(answers, history, lambda a: (_num(a.get("mood")) or 3) <= 2):
        add("low_mood_streak")
    if _streak(answers, history, lambda a: (_num(a.get("anxiety")) or 1) >= 4):
        add("anxiety_streak")
    if _streak(answers, history, lambda a: a.get("meds") == "no"):
        add("missed_meds_streak")

    level = max((REASONS[c][0] for c in reasons), key=ORDER.get, default=GREEN)
    reasons.sort(key=lambda c: -ORDER[REASONS[c][0]])
    return {"level": level, "reasons": reasons}


def reason_text(code, lang="en"):
    entry = REASONS.get(code)
    return entry[1].get(lang, entry[1]["en"]) if entry else code


def reason_level(code):
    return REASONS[code][0] if code in REASONS else YELLOW


def worst(*levels):
    return max(levels, key=lambda l: ORDER.get(l, 0))
