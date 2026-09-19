# Ona — AI pregnancy companion & clinic monitor

"Ona" = "mother" in Uzbek. Hackathon demo (national AI hackathon, Khorezm, Uzbekistan).

## The prompt (what we are building)

Build a demo product with two faces sharing one backend:

1. **Mother app (mobile)** — a pregnant woman opens it once a day and answers a short
   check-in (≈2 minutes, big touch targets, Uzbek first, Russian and English available).
   She immediately gets a warm, plain-language response, a clear "what to do now" when
   something is wrong, and can ask an AI assistant questions about her pregnancy.
2. **Clinic dashboard (web)** — a private clinic sees all its patients sorted by risk,
   gets alerts when a check-in contains a danger sign, opens a patient to see trends
   (blood pressure, weight, mood, symptoms) and an AI-written clinical summary with
   suggested next actions, and can send the patient a message.

AI must *help the process*, not replace the doctor:

- **Safety is deterministic.** Danger signs (bleeding, severe headache + vision changes,
  high BP, reduced fetal movement, fever, fluid leak, …) are detected by a rule engine
  in `triage.py`, based on WHO antenatal-care danger signs. The AI can never lower a
  risk level that the rules assigned.
- **AI adds language and synthesis**: personalised feedback to the mother, a 7-day
  clinical summary for the doctor, and a guard-railed chat assistant.
- **Works offline.** With no API key / no internet, every AI feature falls back to a
  template generated from the rules, so the demo never breaks on stage.

## Constraints

- Machine has **no Node.js** — only system Python 3.9. So: Python stdlib HTTP server +
  SQLite, vanilla HTML/CSS/JS frontend with no build step, installable as a PWA.
- Third-party dependencies: the official `openai` and `anthropic` SDKs in `.venv`. Both are optional at
  runtime; import failure or missing credentials → offline fallback mode.
- **The user runs OpenAI `gpt-5-mini`** (key in `.env` as `OPENAI_API_KEY`): Chat Completions with
  `reasoning_effort`, `max_completion_tokens`, and `response_format` json_schema (strict).
- Anthropic path (used only if an Anthropic key is set instead): model `claude-opus-5`, adaptive thinking (default), `output_config.effort`
  low/medium for latency, structured outputs (`output_config.format`) for JSON,
  server-side refusal fallbacks (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`).
  Always check `stop_reason` before reading content.
- All demo data is synthetic. This is not a medical device; the UI says so.

## Architecture

```
server.py      HTTP server + JSON API + static files   (python stdlib)
db.py          SQLite schema and queries               (ona.db, created on first run)
triage.py      Rule-based risk engine (green / yellow / red) + reasons
ai.py          Claude integration + offline fallbacks
seed.py        Synthetic patients with 14 days of history
questions.py   Daily check-in question set (uz / ru / en)
static/app/    Mother mobile app (PWA)      → http://localhost:8000/
static/clinic/ Clinic dashboard             → http://localhost:8000/clinic
static/demo.html  Stage view (phone + dashboard)  → http://localhost:8000/demo
```

API: `GET /api/questions` · `GET /api/patients` · `GET /api/patients/{id}` ·
`POST /api/checkins` · `POST /api/chat` · `POST /api/patients/{id}/summary` ·
`POST /api/patients/{id}/messages` · `POST /api/alerts/{id}/ack` · `POST /api/demo/reset` · `GET /api/status` · `POST /api/login` · `POST /api/logout` · `GET /api/me`

Auth: clinic staff sign in at `/clinic` (accounts in `seed.STAFF`, shared password from `ONA_CLINIC_PASSWORD`,
default `ona2026`). The patient list, AI summary, alert acknowledgement and clinic-side messaging need a session.
The mother app has no login in this demo, so the endpoints it uses stay open.

## Run

```bash
.venv/bin/python server.py            # offline/template AI mode
.venv/bin/python server.py            # live AI once OPENAI_API_KEY is in .env
.venv/bin/python seed.py --reset      # regenerate demo data
.venv/bin/python -m unittest          # tests
```

Phone on the same Wi-Fi: open `http://<laptop-ip>:8000/` (the server prints the URL).

## Build plan — execute step by step, tick when done

- [x] 1. Backend core: `questions.py`, `triage.py`, `db.py` + unit tests for triage
- [x] 2. `ai.py`: Claude integration with offline fallbacks
- [x] 3. `seed.py` + `server.py`: API and static serving; smoke-test every endpoint
- [x] 4. Mother mobile app (onboarding-free demo login, daily check-in, result, history, chat, i18n)
- [x] 5. Clinic dashboard (risk-sorted list, alerts, patient detail, charts, AI summary, messaging)
- [x] 6. End-to-end verification in a browser, fix bugs
- [x] 7. `README.md` with a 3-minute demo script for the judges
- [x] 9. OpenAI provider (`gpt-5-mini`) alongside Anthropic; `.env` template; provider-neutral UI labels
- [x] 10. Design pass: self-hosted Manrope font (`static/fonts/`), shared SVG icon set (`static/icons.js`) instead of
  emoji in navigation/alerts/buttons, new home screen (status card, quick actions, daily tip), dashboard KPI strip
- [x] 8. Clinic login: staff accounts (PBKDF2 hashes), cookie sessions, protected dashboard endpoints, sign-in screen

## Conventions

- Risk levels are the strings `green`, `yellow`, `red` everywhere.
- Answers are stored as one JSON object per check-in keyed by question id.
- UI chrome uses `icon(name, size)` from `static/icons.js`; emoji stay only where they carry meaning for the mother
  (mood faces, symptom chips).
- All user-facing strings go through the i18n dictionaries (`questions.py`, `static/app/i18n.js`);
  Uzbek uses Latin script.
- Never put medical diagnosis in the mother's UI — only "contact your clinic / call 103".
