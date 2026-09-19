# Ona — AI pregnancy companion and clinic monitor

*Ona* means "mother" in Uzbek. A pregnant woman answers a 2-minute check-in on her phone every day;
her private clinic sees danger signs within seconds, with AI doing the explaining and summarising.

| | |
|---|---|
| Mother app (mobile, UZ / RU / EN) | `http://localhost:8000/` |
| Clinic dashboard (login: `matkarimova` / `ona2026`) | `http://localhost:8000/clinic` |
| Stage view: phone + dashboard side by side | `http://localhost:8000/demo` |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python server.py
```

For live AI responses, put your OpenAI key in the `.env` file next to `server.py`, then restart the server:

```
OPENAI_API_KEY=sk-...
```

The default model is `gpt-5-mini` (change with `ONA_MODEL=`). An `ANTHROPIC_API_KEY` works too (Claude); if both
are set, choose with `ONA_PROVIDER=openai|anthropic`.

Without a key, or without internet, every AI feature falls back to rule-based templates and the
dashboard shows "AI offline mode". The demo never breaks on stage.

On a real phone: connect it to the same Wi-Fi and open the "On a phone" URL the server prints.
Use the browser's "Add to Home Screen" to get a full-screen app icon.

Other commands: `.venv/bin/python seed.py --reset` (fresh demo data) · `.venv/bin/python -m unittest` (triage tests).

## How the AI is used

1. **Deterministic safety net** (`triage.py`): WHO antenatal danger signs as rules — bleeding, fluid leak,
   no fetal movement, BP ≥160/110, pre-eclampsia combinations, preterm contractions and more → RED;
   softer signals and 3-day streaks (low mood, anxiety, missed supplements, >2 kg/week) → YELLOW.
   Covered by unit tests. The AI can never lower a level.
2. **The LLM writes to the mother** (`ai.checkin_feedback`): a warm 2–4 sentence message in her language
   that matches the risk level, with no diagnoses and no medicines.
3. **The LLM briefs the doctor** (`ai.clinical_summary`): structured output (headline, concerns, suggested
   actions, trend) from 14 days of data, risk factors and free-text notes.
4. **The LLM chats and escalates** (`ai.chat`): everyday pregnancy questions; if the mother mentions a
   danger sign in chat, the reply tells her to call and the clinic gets an alert.

Model: OpenAI `gpt-5-mini` through the official `openai` SDK, with structured outputs (JSON schema) for the summary
and the chat. Every call has a 45-second timeout and falls back to templates on any error.

## 3-minute demo script

Open `/demo` on the projector and sign in to the dashboard once (tap the demo-account hint, then *Sign in*); the session
lasts 12 hours and survives **Reset demo data**. If needed, press Reset first.

1. **The problem (20 s).** Between antenatal visits a clinic is blind for 2–4 weeks. Pre-eclampsia and
   reduced fetal movement develop in days. Point at the dashboard: 10 patients, sorted by risk.
2. **The clinic's morning (40 s).** Click *Gulnora Rahimova* (red). Show the BP chart creeping past the
   140/90 line over two weeks, her own words in the log, and the AI summary with suggested actions.
   Mention *Feruza* — flagged as "silent" because she stopped answering 5 days ago.
   Open **Clinical basis** in the header: every rule, its condition and its source, readable by a doctor.
   Press **+ New patient**, register someone, and let a judge scan the QR code with their own phone.
3. **The mother's 2 minutes (60 s).** On the phone (Dilnoza, week 31) press *Boshlash*. Answer normally,
   but select **Qon ketishi** (bleeding) and write a short note. Finish.
   The phone shows a red result with a call button; **within 3 seconds a red alert drops into the
   clinic dashboard** with her note. Click *Open*, then *Acknowledge*, then send her a message — it appears on her
   phone under *Shifokor*.
4. **The chat safety net (30 s).** Switch the phone to *Malika* (week 29), open *Ona AI* and type
   "Bolam bugun kam qimirlayapti". The assistant answers and the clinic receives a chat alert.
5. **Why it is safe (30 s).** Rules decide the risk level, AI explains it. Works offline. Uzbek first.
   Switch the language to RU / EN to show localisation.

## Limitations

Hackathon demo: clinic staff log in (accounts `matkarimova`, `sultonova`, `admin`; set `ONA_CLINIC_PASSWORD` to change the
shared password), but the mother app has no login yet, so patient-side endpoints are open. Synthetic data, not a medical device. Next steps would be SMS/Telegram
reminders, patient login (phone number + SMS code), per-doctor roles, Bluetooth BP cuffs, and clinical validation of thresholds with local
obstetricians.
