"""LLM integration (OpenAI or Anthropic) with offline fallbacks.

Three features, each with a template fallback so the demo works without internet:
  checkin_feedback()  - short message the mother reads after her check-in
  clinical_summary()  - structured 7-day summary for the clinician
  chat()              - guard-railed assistant that can escalate to the clinic

The risk level always comes from triage.py. Prompts tell the model the level is final,
and nothing returned from here is ever used to lower it.
"""
import json
import os
import sys
from collections import Counter

import questions
import triage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
LANG_NAMES = {"uz": "Uzbek (Latin script)", "ru": "Russian", "en": "English"}
DEFAULT_MODELS = {"openai": "gpt-5-mini", "anthropic": "claude-opus-5"}

_client = None
_state = {"mode": "offline", "provider": None, "model": None, "last_error": None, "calls": 0}


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            key, sep, value = line.strip().partition("=")
            value = value.strip().strip("\"'")
            if sep and key and value and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value)


def _pick_provider():
    """ONA_PROVIDER wins; otherwise whichever key is present (OpenAI first)."""
    wanted = os.environ.get("ONA_PROVIDER", "").lower()
    keys = {"openai": os.environ.get("OPENAI_API_KEY"),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")}
    if wanted in keys:
        return wanted if keys[wanted] else None
    return next((name for name in ("openai", "anthropic") if keys[name]), None)


def _get_client():
    global _client
    if _client is None:
        _load_dotenv()
        provider = _pick_provider()
        if not provider:
            return None
        try:
            if provider == "openai":
                import openai
                _client = openai.OpenAI(timeout=45.0, max_retries=1)
            else:
                import anthropic
                _client = anthropic.Anthropic(timeout=45.0, max_retries=1)
            _state.update(mode="live", provider=provider, model=os.environ.get("ONA_MODEL") or DEFAULT_MODELS[provider])
        except Exception as e:  # SDK missing or misconfigured: stay offline
            _state["last_error"] = "SDK init failed: %s" % e
            return None
    return _client


def status():
    _get_client()
    return dict(_state)


def _ask(system, messages, schema=None, effort="low"):
    """One model call. Returns text (or parsed JSON when schema is given), or None to signal fallback."""
    client = _get_client()
    if client is None:
        return None
    try:
        text = (_ask_openai if _state["provider"] == "openai" else _ask_anthropic)(client, system, messages, schema, effort)
        _state["calls"] += 1
        if not text:
            raise RuntimeError("empty response")
        _state["last_error"] = None
        return json.loads(text) if schema else text
    except Exception as e:  # any provider failure means "use the template"; the dashboard chip shows why
        _state["last_error"] = _describe(e)
    print("[ai] falling back to template: %s" % _state["last_error"], file=sys.stderr)
    return None


def _describe(e):
    status = getattr(e, "status_code", None)
    if status == 401:
        return "Invalid API key"
    if status == 429:
        return "Rate limited or out of credit"
    if status:
        return "API error %s: %s" % (status, getattr(e, "message", e))
    if type(e).__name__ in ("APIConnectionError", "APITimeoutError"):
        return "No connection to the AI provider"
    return str(e)


def _ask_openai(client, system, messages, schema, effort):
    import openai

    if not isinstance(system, str):  # Anthropic-style list of text blocks
        system = "\n\n".join(block["text"] for block in system)
    kwargs = dict(model=_state["model"], max_completion_tokens=6000,
                  messages=[{"role": "developer", "content": system}] + messages)
    if schema:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "ona_output", "strict": True, "schema": schema}}
    try:
        resp = client.chat.completions.create(reasoning_effort=effort, **kwargs)
    except openai.BadRequestError as e:  # e.g. a non-reasoning model was configured
        print("[ai] retrying without reasoning_effort: %s" % e.message, file=sys.stderr)
        resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    if choice.finish_reason in ("length", "content_filter") or getattr(choice.message, "refusal", None):
        raise RuntimeError("finish_reason=%s" % choice.finish_reason)
    return (choice.message.content or "").strip()


def _ask_anthropic(client, system, messages, schema, effort):
    import anthropic

    output_config = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs = dict(model=_state["model"], max_tokens=8000, system=system, messages=messages, output_config=output_config)
    try:
        # a declined request is re-run server-side on Anthropic's recommended fallback model
        resp = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
    except anthropic.BadRequestError as e:
        print("[ai] retrying without fallbacks: %s" % e.message, file=sys.stderr)
        resp = client.messages.create(**kwargs)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError("stop_reason=%s" % resp.stop_reason)
    return next((b.text for b in resp.content if b.type == "text"), "").strip()


def _L(lang, uz, ru, en):
    return {"uz": uz, "ru": ru, "en": en}.get(lang, en)


def _first_name(patient):
    return patient["name"].split()[0]


def _compact_checkin(c, lang="en"):
    a = c["answers"]
    out = {"day": c["day"], "risk": c["level"], "flags": [triage.reason_text(r, "en") for r in c["reasons"]],
           "mood_1to5": a.get("mood"), "anxiety_1to5": a.get("anxiety"),
           "symptoms": [questions.label(s, "en") for s in a.get("symptoms", []) if s != "none"],
           "sleep": a.get("sleep"), "supplements_taken": a.get("meds")}
    for key in ("headache_severity", "movement", "weight", "note"):
        if a.get(key) not in (None, ""):
            out["fetal_movement" if key == "movement" else key] = a[key]
    bp = a.get("bp") or {}
    if bp.get("sys") and bp.get("dia"):
        out["bp"] = "%s/%s" % (bp["sys"], bp["dia"])
    return out


def _patient_card(patient):
    return json.dumps({"first_name": _first_name(patient), "age": patient.get("age"),
                       "gestational_week": patient["week"], "known_risk_factors": patient["risk_factors"]},
                      ensure_ascii=False)


# ---- 1. feedback to the mother ---------------------------------------------

FEEDBACK_SYSTEM = """You are Ona, the voice of a pregnancy-monitoring app that private clinics in Uzbekistan give to their patients. A mother has just finished her daily check-in and will read your message on her phone straight away.

A rule-based triage engine has already assigned today's risk level, and that level is final: your job is to put it into kind, plain words, not to re-assess it. She is not a clinician, so avoid diagnosis names (say "these signs need a doctor's attention", not "pre-eclampsia") and never suggest medicines or doses; her clinic does that.

How the message should feel at each level:
- green: warm and brief. Acknowledge something specific she reported, and add one small practical tip that fits her week of pregnancy or her answers (sleep, water, supplements, worry).
- yellow: calm, not alarming. Say her clinic will see these answers today, what to watch for, and that she should call the clinic if it gets worse.
- red: clear and direct, because minutes can matter. Tell her to call her clinic now, or 103 if she cannot reach them, and not to wait for the next check-in. The app shows a call button under your message. Stay caring; do not frighten her with worst cases.

Write 2-4 short sentences in the language requested, addressing her by first name. Plain text only: no markdown, no lists, no emoji beyond at most one."""


def checkin_feedback(patient, answers, result, lang):
    today = {"answers": _compact_checkin({"day": "today", "answers": answers, "level": result["level"], "reasons": result["reasons"]})}
    prompt = "Mother: %s\nToday's check-in: %s\nRisk level from triage: %s\nWrite the message in %s." % (
        _patient_card(patient), json.dumps(today, ensure_ascii=False), result["level"].upper(), LANG_NAMES.get(lang, "English"))
    text = _ask(FEEDBACK_SYSTEM, [{"role": "user", "content": prompt}])
    if text:
        return {"text": text, "source": "ai"}
    return {"text": _feedback_template(patient, answers, result, lang), "source": "template"}


def _feedback_template(patient, answers, result, lang):
    name, level = _first_name(patient), result["level"]
    if level == triage.RED:
        return _L(lang,
                  "%s, bugungi javoblaringizdagi belgilar shifokor e'tiborini darhol talab qiladi. Iltimos, hoziroq klinikangizga qo'ng'iroq qiling, bog'lana olmasangiz 103 ga qo'ng'iroq qiling. Keyingi so'rovnomani kutmang." % name,
                  "%s, признаки из ваших сегодняшних ответов требуют срочного внимания врача. Пожалуйста, позвоните в клинику прямо сейчас, а если не дозвонитесь — в 103. Не ждите следующего опроса." % name,
                  "%s, the signs in today's answers need a doctor's attention right away. Please call your clinic now, or 103 if you cannot reach them. Do not wait for the next check-in." % name)
    if level == triage.YELLOW:
        return _L(lang,
                  "Rahmat, %s. Bugungi ba'zi javoblaringizni shifokoringiz bugunoq ko'rib chiqadi. Ko'proq dam oling va suv iching. Agar ahvolingiz yomonlashsa, klinikaga qo'ng'iroq qiling." % name,
                  "Спасибо, %s. Некоторые из ваших ответов врач посмотрит уже сегодня. Побольше отдыхайте и пейте воду. Если станет хуже — позвоните в клинику." % name,
                  "Thank you, %s. Your doctor will look at some of today's answers today. Rest and drink water. If anything gets worse, call your clinic." % name)
    if answers.get("meds") == "no":
        tip = _L(lang, "Bugun vitamin va temir preparatini ichishni unutmang.", "Не забудьте сегодня принять витамины и железо.", "Remember to take your vitamins and iron today.")
    elif answers.get("sleep") == "lt5":
        tip = _L(lang, "Kunduzi 20–30 daqiqa dam olishga harakat qiling — uyqu siz va bolangiz uchun muhim.", "Постарайтесь отдохнуть днём 20–30 минут — сон важен для вас и малыша.", "Try a 20–30 minute rest during the day — sleep matters for you and your baby.")
    else:
        tip = _L(lang, "Kun davomida 8 stakan suv ichishni va ozroq sayr qilishni unutmang.", "Не забывайте выпивать около 8 стаканов воды и немного гулять.", "Keep drinking about 8 glasses of water and take a short walk.")
    return _L(lang, "Rahmat, %s! Bugungi javoblaringiz yaxshi ko'rinadi. %s" % (name, tip),
              "Спасибо, %s! Сегодня всё выглядит хорошо. %s" % (name, tip),
              "Thank you, %s! Everything looks good today. %s" % (name, tip))


# ---- 2. clinical summary for the clinic ------------------------------------

SUMMARY_SYSTEM = """You support obstetricians at a private clinic in Uzbekistan that monitors pregnant patients between visits through a daily self-report app. Given one patient's recent check-ins, write the briefing a busy doctor reads in 20 seconds before deciding whether to call her.

The data is self-reported by the patient at home; blood pressure and weight come from her own devices and may be missing. Each check-in already carries a risk level and flags from a deterministic rule engine based on WHO danger signs. Treat those flags as given, and add what rules cannot: patterns across days (BP creeping up, weight jumps, mood sliding, supplements skipped, check-ins stopping), how the findings interact with her known risk factors and gestational week, and anything important in her free-text notes.

Be specific and numeric ("BP 128/82 -> 146/94 over 5 days"), and say when data is too thin to judge. Suggested actions are options for the doctor to consider (call today, bring the visit forward, urine protein test, repeat BP in clinic), ordered by urgency; the doctor decides. Do not invent measurements that are not in the data.

Fields:
- headline: one line, under 90 characters, the single most important thing.
- summary: 2-4 sentences.
- concerns: zero to four short items, most serious first. Empty if there are none.
- suggested_actions: one to four short items.
- trend: improving, stable, or worsening over the period."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "concerns": {"type": "array", "items": {"type": "string"}},
        "suggested_actions": {"type": "array", "items": {"type": "string"}},
        "trend": {"type": "string", "enum": ["improving", "stable", "worsening"]},
    },
    "required": ["headline", "summary", "concerns", "suggested_actions", "trend"],
    "additionalProperties": False,
}


def clinical_summary(patient, checkins, lang):
    data = [_compact_checkin(c) for c in reversed(checkins[:14])]
    prompt = "Patient: %s\nCheck-ins, oldest first (days with no entry were missed): %s\nWrite every field in %s." % (
        _patient_card(patient), json.dumps(data, ensure_ascii=False), LANG_NAMES.get(lang, "English"))
    body = _ask(SUMMARY_SYSTEM, [{"role": "user", "content": prompt}], schema=SUMMARY_SCHEMA, effort="medium") if checkins else None
    if body:
        return dict(body, source="ai")
    return dict(_summary_template(patient, checkins, lang), source="template")


def _summary_template(patient, checkins, lang):
    week = checkins[:7]
    if not week:
        return {"headline": _L(lang, "Hali so'rovnoma to'ldirilmagan", "Опросов пока нет", "No check-ins yet"), "summary": "",
                "concerns": [], "suggested_actions": [_L(lang, "Bemorga qo'ng'iroq qilib, ilovadan foydalanishni eslating", "Позвонить пациентке и напомнить о приложении", "Call the patient and remind her to use the app")],
                "trend": "stable"}
    levels = Counter(c["level"] for c in week)
    flags = Counter(r for c in week for r in c["reasons"])
    score = lambda cs: sum(triage.ORDER[c["level"]] for c in cs) / float(len(cs)) if cs else 0
    recent, older = score(week[:3]), score(week[3:])
    trend = "worsening" if recent > older + 0.3 else "improving" if recent < older - 0.3 else "stable"
    bps = [(c["day"], c["answers"]["bp"]) for c in reversed(week) if (c["answers"].get("bp") or {}).get("sys")]
    concerns = ["%s ×%d" % (triage.reason_text(code, lang), n) for code, n in flags.most_common(4)]
    if len(bps) >= 2:
        concerns.append(_L(lang, "Qon bosimi: ", "АД: ", "BP: ") + " → ".join("%s/%s" % (b["sys"], b["dia"]) for _, b in bps[-4:]))
    worst = triage.worst(*[c["level"] for c in week])
    actions = {
        triage.RED: _L(lang, "Bugun bemorga qo'ng'iroq qiling va ko'rikka chaqiring", "Позвонить пациентке сегодня и пригласить на осмотр", "Call the patient today and bring her in for assessment"),
        triage.YELLOW: _L(lang, "24 soat ichida bog'laning, keyingi ko'rikni yaqinlashtirishni ko'rib chiqing", "Связаться в течение 24 часов, рассмотреть перенос визита на более ранний срок", "Contact within 24 hours; consider bringing the next visit forward"),
        triage.GREEN: _L(lang, "Rejali kuzatuvni davom ettiring", "Продолжать плановое наблюдение", "Continue routine monitoring"),
    }[worst]
    headline = _L(lang, "7 kunda %d ta so'rovnoma: %d qizil, %d sariq", "%d опросов за 7 дней: %d красных, %d жёлтых", "%d check-ins in 7 days: %d red, %d yellow") % (
        len(week), levels[triage.RED], levels[triage.YELLOW])
    summary = _L(lang, "Homiladorlikning %d-haftasi. Xavf omillari: %s. (Oflayn rejim — qoidalar asosidagi xulosa.)",
                 "%d-я неделя беременности. Факторы риска: %s. (Офлайн-режим — сводка на основе правил.)",
                 "Week %d of pregnancy. Risk factors: %s. (Offline mode — rule-based summary.)") % (
        patient["week"], ", ".join(patient["risk_factors"]) or "—")
    return {"headline": headline, "summary": summary, "concerns": concerns, "suggested_actions": [actions], "trend": trend}


# ---- 3. assistant chat ------------------------------------------------------

CHAT_SYSTEM = """You are Ona, a pregnancy companion inside an app that a private clinic in Uzbekistan gives to its patients. Mothers ask you everyday questions: food, sleep, nausea, what is normal at their week, worries, how to prepare for birth. Many are first-time mothers, some live far from the clinic, and you may be the first place they mention a symptom.

Answer like a knowledgeable, kind midwife would in a short phone message: a few sentences, plain words, in the language the mother writes in (default to the requested language). Use what you know about her week and recent check-ins to make answers personal. Respect local life: family and food customs in Khorezm are part of her world, so work with them unless something is actually unsafe.

You are not her doctor. Do not diagnose, and do not recommend medicines, doses or herbal remedies; for those, say her clinic doctor will advise and offer to pass the question on. General, widely accepted guidance (hydration, rest, food safety, when to seek care) is what you are here for.

Escalation matters more than anything else you do. If her message describes something that could be a danger sign (bleeding, fluid leaking, severe or persistent headache, vision changes, sudden swelling, strong abdominal pain, fever, the baby moving less, regular contractions before term, difficulty breathing, fainting, thoughts of harming herself, or violence at home), tell her clearly to call the clinic now (or 103 if she cannot reach them) and set escalate accordingly, so the clinic is alerted even if she does not call:
- "urgent": possible emergency, she should be seen or called today, now.
- "soon": not an emergency, but the clinic should follow up within a day (persistent low mood, a worry she keeps returning to, a medication question only a doctor can answer).
- "none": ordinary conversation.
When unsure between two levels, choose the higher one. escalate_reason is one short English sentence for the clinic (empty when "none")."""

CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "escalate": {"type": "string", "enum": ["none", "soon", "urgent"]},
        "escalate_reason": {"type": "string"},
    },
    "required": ["reply", "escalate", "escalate_reason"],
    "additionalProperties": False,
}

DANGER_WORDS = {
    "urgent": ["qon ket", "qon kel", "suv ket", "qimirlama", "harakat qilma", "to'lg'oq", "tolg'oq", "nafas", "hushdan", "ko'rmayap", "xira",
               "кров", "воды отошли", "подтека", "не шевел", "схватк", "задыха", "обморок", "в глазах", "мушки",
               "bleed", "leak", "not moving", "no movement", "contraction", "breath", "faint", "blurred", "vision"],
    "soon": ["bosh og'ri", "isitma", "shish", "qus", "og'riq", "yig'la", "qo'rq",
             "голов", "температур", "отёк", "отек", "рвот", "боль", "болит", "плач", "страшно",
             "headache", "fever", "swell", "vomit", "pain", "crying", "scared", "depress"],
}


def chat(patient, history, recent_checkins, lang):
    """history: list of {"sender": "patient"|"ai", "text": ...}, oldest first, ending with the new patient message."""
    msgs = [{"role": "user" if m["sender"] == "patient" else "assistant", "content": m["text"]} for m in history[-16:]]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    context = "About this mother: %s\nHer last check-ins: %s\nDefault reply language: %s." % (
        _patient_card(patient), json.dumps([_compact_checkin(c) for c in recent_checkins[:5]], ensure_ascii=False),
        LANG_NAMES.get(lang, "English"))
    out = _ask([{"type": "text", "text": CHAT_SYSTEM}, {"type": "text", "text": context}], msgs, schema=CHAT_SCHEMA)
    if out:
        return dict(out, source="ai")
    return dict(_chat_template(history[-1]["text"], lang), source="template")


def _chat_template(text, lang):
    low = text.lower()
    for level in ("urgent", "soon"):
        hit = next((w for w in DANGER_WORDS[level] if w in low), None)
        if hit and level == "urgent":
            return {"escalate": "urgent", "escalate_reason": "Chat message mentions a possible danger sign (keyword: %s)." % hit,
                    "reply": _L(lang, "Bu muhim belgi bo'lishi mumkin. Iltimos, hoziroq klinikangizga qo'ng'iroq qiling yoki 103 ga murojaat qiling. Men klinikangizga xabar yubordim.",
                                "Это может быть важным признаком. Пожалуйста, позвоните в клинику прямо сейчас или в 103. Я уже сообщила вашей клинике.",
                                "This could be an important sign. Please call your clinic now, or 103. I have alerted your clinic.")}
        if hit:
            return {"escalate": "soon", "escalate_reason": "Chat message mentions a symptom or distress (keyword: %s)." % hit,
                    "reply": _L(lang, "Tushunaman, bu sizni bezovta qilyapti. Savolingizni shifokoringizga yubordim — ular siz bilan bog'lanishadi. Agar kuchaysa, klinikaga qo'ng'iroq qiling.",
                                "Понимаю, что это вас беспокоит. Я передала ваш вопрос врачу — с вами свяжутся. Если станет хуже, позвоните в клинику.",
                                "I understand this is worrying you. I have passed it to your doctor, who will contact you. If it gets worse, call your clinic.")}
    return {"escalate": "none", "escalate_reason": "",
            "reply": _L(lang, "Yaxshi savol! Hozir oflayn rejimdaman, shuning uchun qisqa javob beraman: yaxshi ovqatlaning, ko'proq suv iching va dam oling. Aniq maslahat uchun savolingizni shifokoringizga yuborishim mumkin.",
                        "Хороший вопрос! Сейчас я работаю офлайн, поэтому отвечу кратко: полноценно питайтесь, пейте больше воды и отдыхайте. За точным советом могу передать вопрос вашему врачу.",
                        "Good question! I'm in offline mode right now, so briefly: eat well, drink plenty of water and rest. For specific advice I can pass your question to your doctor.")}
