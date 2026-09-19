"""Daily check-in question set, localized in Uzbek (Latin), Russian and English.

Question types understood by the mobile app:
  scale   - 1..5 faces
  multi   - multi-select chips; the option with exclusive=True clears the others
  choice  - single select
  bp      - two optional numbers (systolic / diastolic)
  number  - one optional number
  text    - optional free text

`show_if` is evaluated on the client and re-checked by triage:
  {"min_week": 24}                      only from that gestational week
  {"symptom": "headache"}               only if that symptom was selected
"""

LANGS = ("uz", "ru", "en")


def T(uz, ru, en):
    return {"uz": uz, "ru": ru, "en": en}


SYMPTOMS = [
    {"id": "headache", "icon": "🤕", "label": T("Bosh og'rig'i", "Головная боль", "Headache")},
    {"id": "vision", "icon": "👁️", "label": T("Ko'z xiralashishi yoki uchqunlar", "Пелена или мушки перед глазами", "Blurred vision or flashing lights")},
    {"id": "swelling", "icon": "🖐️", "label": T("Yuz yoki qo'llar shishi", "Отёк лица или рук", "Swelling of face or hands")},
    {"id": "bleeding", "icon": "🩸", "label": T("Qon ketishi", "Кровянистые выделения", "Vaginal bleeding")},
    {"id": "fluid_leak", "icon": "💧", "label": T("Suv ketishi", "Подтекание вод", "Leaking fluid")},
    {"id": "abdominal_pain", "icon": "⚡", "label": T("Qorinda kuchli og'riq", "Сильная боль в животе", "Severe abdominal pain")},
    {"id": "contractions", "icon": "⏱️", "label": T("Muntazam to'lg'oqlar", "Регулярные схватки", "Regular contractions")},
    {"id": "breathless", "icon": "😮‍💨", "label": T("Nafas qisishi", "Одышка, трудно дышать", "Difficulty breathing")},
    {"id": "fever", "icon": "🌡️", "label": T("Isitma (38°C dan yuqori)", "Температура выше 38°C", "Fever (above 38°C)")},
    {"id": "vomiting", "icon": "🤢", "label": T("To'xtovsiz qusish", "Многократная рвота", "Persistent vomiting")},
    {"id": "dizziness", "icon": "💫", "label": T("Bosh aylanishi", "Головокружение", "Dizziness")},
    {"id": "urination", "icon": "🚻", "label": T("Siyishda achishish", "Жжение при мочеиспускании", "Burning when urinating")},
    {"id": "none", "icon": "✅", "exclusive": True, "label": T("Hech qaysi biri", "Ничего из этого", "None of these")},
]

QUESTIONS = [
    {
        "id": "mood", "type": "scale",
        "text": T("Bugun o'zingizni qanday his qilyapsiz?", "Как вы себя чувствуете сегодня?", "How are you feeling today?"),
        "low": T("Juda yomon", "Очень плохо", "Very bad"),
        "high": T("Juda yaxshi", "Отлично", "Great"),
    },
    {
        "id": "symptoms", "type": "multi",
        "text": T("Bugun quyidagilardan birortasi bo'ldimi?", "Было ли сегодня что-то из этого?", "Did you have any of these today?"),
        "options": SYMPTOMS,
    },
    {
        "id": "headache_severity", "type": "choice", "show_if": {"symptom": "headache"},
        "text": T("Bosh og'rig'i qanchalik kuchli?", "Насколько сильная головная боль?", "How strong is the headache?"),
        "options": [
            {"id": "mild", "label": T("Yengil", "Слабая", "Mild")},
            {"id": "moderate", "label": T("O'rtacha", "Умеренная", "Moderate")},
            {"id": "severe", "label": T("Kuchli, dori yordam bermayapti", "Сильная, лекарства не помогают", "Severe, medicine does not help")},
        ],
    },
    {
        "id": "movement", "type": "choice", "show_if": {"min_week": 24},
        "text": T("Bolangiz bugun qanday qimirladi?", "Как сегодня шевелился малыш?", "How did your baby move today?"),
        "options": [
            {"id": "normal", "icon": "👶", "label": T("Odatdagidek", "Как обычно", "As usual")},
            {"id": "less", "icon": "🔅", "label": T("Odatdagidan kamroq", "Меньше обычного", "Less than usual")},
            {"id": "none", "icon": "⚠️", "label": T("Umuman sezmadim", "Совсем не чувствовала", "I felt no movement")},
        ],
    },
    {
        "id": "bp", "type": "bp", "optional": True,
        "text": T("Qon bosimingizni o'lchadingizmi?", "Измеряли ли вы давление?", "Did you measure your blood pressure?"),
        "hint": T("Tonometr bo'lmasa, o'tkazib yuboring", "Если нет тонометра — пропустите", "Skip if you have no monitor"),
    },
    {
        "id": "weight", "type": "number", "optional": True, "unit": "kg", "min": 35, "max": 160, "step": 0.1,
        "text": T("Bugungi vazningiz?", "Ваш вес сегодня?", "Your weight today?"),
        "hint": T("Ixtiyoriy", "Необязательно", "Optional"),
    },
    {
        "id": "sleep", "type": "choice",
        "text": T("Kecha qancha uxladingiz?", "Сколько вы спали прошлой ночью?", "How much did you sleep last night?"),
        "options": [
            {"id": "lt5", "label": T("5 soatdan kam", "Меньше 5 часов", "Less than 5 hours")},
            {"id": "5to7", "label": T("5–7 soat", "5–7 часов", "5–7 hours")},
            {"id": "gt7", "label": T("7 soatdan ko'p", "Больше 7 часов", "More than 7 hours")},
        ],
    },
    {
        "id": "anxiety", "type": "scale",
        "text": T("Bugun qanchalik xavotirdasiz?", "Насколько вы сегодня тревожитесь?", "How worried or anxious are you today?"),
        "low": T("Xotirjamman", "Спокойна", "Calm"),
        "high": T("Juda xavotirdaman", "Очень тревожно", "Very anxious"),
        "inverted": True,
    },
    {
        "id": "meds", "type": "choice",
        "text": T("Bugun vitamin va temir preparatlarini ichdingizmi?", "Принимали сегодня витамины и железо?", "Did you take your vitamins and iron today?"),
        "options": [
            {"id": "yes", "icon": "💊", "label": T("Ha", "Да", "Yes")},
            {"id": "no", "icon": "✖️", "label": T("Yo'q", "Нет", "No")},
        ],
    },
    {
        "id": "note", "type": "text", "optional": True,
        "text": T("Shifokoringizga aytmoqchi bo'lgan gapingiz bormi?", "Хотите что-то сообщить врачу?", "Anything you want to tell your doctor?"),
        "hint": T("Ixtiyoriy — o'z so'zlaringiz bilan yozing", "Необязательно — напишите своими словами", "Optional — write in your own words"),
    },
]

SYMPTOM_LABELS = {s["id"]: s["label"] for s in SYMPTOMS}


def label(symptom_id, lang="en"):
    return SYMPTOM_LABELS.get(symptom_id, {}).get(lang, symptom_id)
