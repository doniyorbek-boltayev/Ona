// Ona mother app — vanilla JS, no build step. All text goes through h()/textContent, never innerHTML.
const params = new URLSearchParams(location.search);
const S = {
  pid: +params.get("p") || 1,
  lang: params.get("lang") || localStorage.getItem("ona.lang") || "uz",
  tab: "home",
  meta: null, data: null,
  flow: null,     // {i, answers} while a check-in is in progress
  result: null,   // last check-in response
  aiExtra: [],    // escalation notes shown in the AI chat this session
  busy: false,
};
const FACES = ["😣", "🙁", "😐", "🙂", "😄"];
const FACES_INVERTED = ["😌", "🙂", "😐", "😟", "😰"];
const SIZE_EMOJI = ["🌱", "🍒", "🍋", "🍎", "🥭", "🌽", "🍆", "🥥", "🍈", "🍉"];
const LEVEL_ICON = { green: "check-circle", yellow: "alert-triangle", red: "alert-octagon" };

const view = document.getElementById("view");
const tabs = document.getElementById("tabs");

function t(key, vars) {
  let s = (I18N[S.lang] || I18N.en)[key] ?? key;
  for (const k in vars || {}) s = s.replace("{" + k + "}", vars[k]);
  return s;
}
const loc = (obj) => (obj && (obj[S.lang] || obj.en)) || "";

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || res.statusText);
  return json;
}

function toast(text) {
  const el = h("div", { class: "toast" }, text);
  document.getElementById("phone").append(el);
  setTimeout(() => el.remove(), 3000);
}

async function load() {
  S.data = await api(`/api/patients/${S.pid}?lang=${S.lang}`);
}

const UZ_MONTHS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];  // browsers ship no Uzbek month names
function fmtTime(iso) {
  const day = S.lang === "uz" ? `${+iso.slice(8, 10)}-${UZ_MONTHS[+iso.slice(5, 7) - 1]}`
    : new Date(iso).toLocaleDateString(S.lang === "en" ? "en-GB" : "ru-RU", { day: "numeric", month: "short" });
  return day + " · " + iso.slice(11, 16);
}

// ---- shell -------------------------------------------------------------------

function render() {
  document.documentElement.lang = S.lang;
  const full = S.flow || S.result || S.busy;
  tabs.classList.toggle("hidden", !!full);
  view.replaceChildren(S.busy ? Analysing() : S.result ? Result() : S.flow ? Flow() : { home: Home, ai: AiChat, clinic: ClinicChat, history: History }[S.tab]());
  const unread = S.data.clinic_messages.length && S.data.clinic_messages.at(-1).sender === "clinic"
    && S.data.clinic_messages.at(-1).id > +(localStorage.getItem("ona.seen." + S.pid) || 0);
  tabs.replaceChildren(...[["home", "home", "tabHome"], ["ai", "sparkles", "tabAI"], ["clinic", "message", "tabClinic"], ["history", "calendar", "tabHistory"]].map(([id, ic, key]) =>
    h("button", { class: S.tab === id ? "on" : "", onclick: () => go(id) }, h("span", { class: "ic" }, icon(ic, 22)), t(key), id === "clinic" && unread && S.tab !== "clinic" ? h("i", { class: "dot" }) : null)));
  const msgs = view.querySelector(".msgs");
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

function go(tab) {
  S.tab = tab;
  if (tab === "clinic" && S.data.clinic_messages.length) localStorage.setItem("ona.seen." + S.pid, S.data.clinic_messages.at(-1).id);
  render();
}

function Langs() {
  return h("div", { class: "langs" }, S.meta.langs.map((l) => h("button", { class: l === S.lang ? "on" : "", onclick: () => { S.lang = l; localStorage.setItem("ona.lang", l); render(); } }, l.toUpperCase())));
}

// ---- home --------------------------------------------------------------------

function Home() {
  const p = S.data.patient;
  const daysLeft = Math.max(0, Math.round((new Date(p.due_date) - new Date()) / 864e5));
  const sizeIdx = SIZE_BY_WEEK.find(([w]) => p.week <= w)[1];
  const size = I18N[S.lang].sizes[sizeIdx];
  const tri = (from, to) => Math.max(0, Math.min(100, (p.week - from) / (to - from) * 100));
  const today = S.data.today;
  const lastClinic = S.data.clinic_messages.filter((m) => m.sender === "clinic").at(-1);
  const tip = I18N[S.lang].tips[p.week < 14 ? 0 : p.week < 28 ? 1 : 2];
  const long = today && today.feedback && today.feedback.length > 150;

  return h("div", {},
    h("header", { class: "hero" },
      h("div", { class: "hero-top" }, h("div", { class: "brand" }, h("img", { src: "/static/icon.svg", alt: "" }), "Ona"), Langs()),
      h("div", { class: "hello" }, h("div", { class: "avatar" }, p.name.split(" ").map((w) => w[0]).join("").slice(0, 2)),
        h("div", {}, h("h1", {}, `${t("hello")}, ${p.name.split(" ")[0]}!`), h("p", {}, `${S.data.clinic.name} · ${p.doctor}`)))),
    h("div", { class: "stack lift" },
      h("section", { class: "card" },
        h("div", { class: "row" },
          h("div", { class: "ring", style: `--p:${Math.min(100, p.week / 40 * 100)}` }, h("div", {}, h("b", {}, p.week), h("span", {}, t("week")))),
          h("div", { class: "grow" }, h("h3", {}, t("weekOf", { w: p.week })), h("div", { class: "muted" }, t("daysLeft", { d: daysLeft })))),
        h("div", { class: "trimesters" }, [[0, 13], [13, 27], [27, 40]].map(([a, b], i) =>
          h("div", { class: "tri" + (p.week > a && p.week <= b ? " now" : "") }, h("i", {}, h("u", { style: `width:${tri(a, b)}%` })), h("span", {}, `${i + 1}-${t("trimester")}`)))),
        h("div", { class: "baby" }, h("div", { class: "fruit" }, SIZE_EMOJI[sizeIdx]), h("div", { class: "muted" }, t("babySize", { x: size })))),
      today
        ? h("section", { class: "card status " + today.level },
            h("div", { class: "row" }, h("div", { class: "badge " + today.level }, icon(LEVEL_ICON[today.level], 26)),
              h("div", { class: "grow" }, h("div", { class: "muted" }, t("doneToday")), h("h3", {}, t("level_" + today.level)))),
            today.feedback ? h("p", { class: "feedback" + (long && !S.expanded ? " clamp" : "") }, today.feedback) : null,
            long ? h("button", { class: "link", onclick: () => { S.expanded = !S.expanded; render(); } }, t(S.expanded ? "less" : "more")) : null,
            today.level !== "green" ? h("a", { class: "btn" + (today.level === "red" ? " danger" : ""), style: "margin-top:12px", href: "tel:" + S.data.clinic.phone.replace(/\s/g, "") }, icon("phone", 18), t("callClinic")) : null,
            h("button", { class: "btn plain small", onclick: startFlow }, t("redo")))
        : h("section", { class: "card cta" },
            h("div", { class: "row" }, h("div", { class: "badge glass" }, icon("clipboard", 26)),
              h("div", { class: "grow" }, h("h3", {}, t("checkinTitle")), h("div", { class: "muted" }, t("checkinSub")))),
            h("button", { class: "btn", onclick: startFlow }, t("start"), icon("arrow-right", 18))),
      h("div", { class: "quick" },
        h("button", { onclick: () => go("ai") }, h("div", { class: "badge soft" }, icon("sparkles", 20)), t("askAI")),
        h("button", { onclick: () => go("clinic") }, h("div", { class: "badge soft" }, icon("message", 20)), t("writeDoctor"))),
      h("section", { class: "card" },
        h("div", { class: "row", style: "justify-content:space-between" }, h("h3", {}, t("last14")), h("span", { class: "pill" }, icon("flame", 14), t("streak", { n: S.data.streak }))),
        h("div", { class: "dots" }, p.timeline.map((lv) => h("i", { class: lv || "" })))),
      lastClinic ? h("section", { class: "card tap", onclick: () => go("clinic") },
        h("div", { class: "row" }, h("div", { class: "badge soft" }, icon("user", 20)),
          h("div", { class: "grow" }, h("div", { class: "muted" }, t("fromClinic") + " · " + p.doctor), h("p", { style: "margin:2px 0 0" }, lastClinic.text)))) : null,
      h("section", { class: "card tip" }, h("div", { class: "row", style: "align-items:flex-start" }, h("div", { class: "badge warm" }, icon("lightbulb", 20)),
        h("div", { class: "grow" }, h("div", { class: "muted" }, t("tipTitle")), h("p", { style: "margin:2px 0 0" }, tip)))),
      h("p", { class: "foot" }, t("disclaimer"))));
}

// ---- check-in flow -----------------------------------------------------------

function visibleQuestions() {
  const week = S.data.patient.week, a = S.flow.answers;
  return S.meta.questions.filter((q) => {
    const c = q.show_if || {};
    if (c.min_week && week < c.min_week) return false;
    if (c.symptom && !(a.symptoms || []).includes(c.symptom)) return false;
    return true;
  });
}

function startFlow() { S.flow = { i: 0, answers: {} }; S.result = null; render(); }

function step(delta) {
  const qs = visibleQuestions();
  const i = S.flow.i + delta;
  if (i < 0) { S.flow = null; return render(); }
  if (i >= qs.length) return submit();
  S.flow.i = i;
  render();
}

function Flow() {
  const qs = visibleQuestions();
  const q = qs[S.flow.i], a = S.flow.answers, last = S.flow.i === qs.length - 1;
  const pick = (value, auto) => {
    a[q.id] = value; render();
    clearTimeout(S.flow.timer);  // a quick double tap must not skip the next question
    if (auto) S.flow.timer = setTimeout(() => step(1), 220);
  };
  let body, ready = a[q.id] != null;

  if (q.type === "scale") {
    const faces = q.inverted ? FACES_INVERTED : FACES;
    body = [h("div", { class: "faces" }, faces.map((f, n) => h("button", { class: a[q.id] === n + 1 ? "on" : "", onclick: () => pick(n + 1, true) }, f))),
      h("div", { class: "ends" }, h("span", {}, loc(q.low)), h("span", {}, loc(q.high)))];
  } else if (q.type === "choice") {
    body = h("div", { class: "opts" }, q.options.map((o) => h("button", { class: "opt" + (a[q.id] === o.id ? " on" : ""), onclick: () => pick(o.id, true) },
      o.icon ? h("span", { class: "e" }, o.icon) : null, loc(o.label))));
  } else if (q.type === "multi") {
    const sel = a[q.id] || [];
    const toggle = (o) => {
      let next = sel.includes(o.id) ? sel.filter((x) => x !== o.id) : [...sel, o.id];
      const exclusive = q.options.filter((x) => x.exclusive).map((x) => x.id);
      next = o.exclusive ? (next.includes(o.id) ? [o.id] : []) : next.filter((x) => !exclusive.includes(x));
      if (!next.includes("headache")) delete a.headache_severity;
      a[q.id] = next; render();
    };
    body = h("div", { class: "opts two" }, q.options.map((o) => h("button", { class: "opt" + (sel.includes(o.id) ? " on" : ""), onclick: () => toggle(o),
      style: o.exclusive ? "grid-column:1/-1" : "" }, h("span", { class: "e" }, o.icon), loc(o.label))));
    ready = sel.length > 0;
  } else if (q.type === "bp") {
    const v = a.bp || {};
    const set = (k) => (e) => { a.bp = { ...(a.bp || {}), [k]: e.target.value }; };
    body = h("div", { class: "fields" },
      h("div", { class: "field" }, h("label", {}, t("sys")), h("input", { type: "number", inputmode: "numeric", placeholder: "120", value: v.sys || "", oninput: set("sys") })),
      h("div", { class: "slash" }, "/"),
      h("div", { class: "field" }, h("label", {}, t("dia")), h("input", { type: "number", inputmode: "numeric", placeholder: "80", value: v.dia || "", oninput: set("dia") })));
    ready = true;
  } else if (q.type === "number") {
    body = h("div", { class: "fields" }, h("div", { class: "field" }, h("label", {}, q.unit),
      h("input", { type: "number", inputmode: "decimal", step: q.step, min: q.min, max: q.max, placeholder: "—", value: a[q.id] ?? "", oninput: (e) => { a[q.id] = e.target.value === "" ? null : +e.target.value; } })));
    ready = true;
  } else {
    body = h("textarea", { placeholder: "…", oninput: (e) => { a[q.id] = e.target.value; } }, a[q.id] || "");
    ready = true;
  }

  const auto = q.type === "scale" || q.type === "choice";
  return h("div", { class: "flow" },
    h("div", { class: "flow-top" }, h("button", { onclick: () => step(-1), "aria-label": t("back") }, icon("arrow-left", 20)),
      h("div", { class: "bar" }, h("i", { style: `width:${(S.flow.i + 1) / qs.length * 100}%` })),
      h("span", { class: "muted" }, `${S.flow.i + 1}/${qs.length}`)),
    h("div", { class: "q" }, h("h2", {}, loc(q.text)), q.hint ? h("p", { class: "hint" }, loc(q.hint)) : null, body),
    h("div", { class: "flow-actions" },
      auto && !ready ? null : h("button", { class: "btn", disabled: !ready, onclick: () => step(1) }, last ? t("finish") : t("next")),
      q.optional && !last ? h("button", { class: "btn plain", onclick: () => { delete a[q.id]; step(1); } }, t("skip")) : null));
}

async function submit() {
  const answers = S.flow.answers;
  if (answers.bp && !(answers.bp.sys && answers.bp.dia)) delete answers.bp;
  S.busy = true; render();
  try {
    const [res] = await Promise.all([api("/api/checkins", { patient_id: S.pid, lang: S.lang, answers }), new Promise((r) => setTimeout(r, 1400))]);
    S.result = res; S.flow = null;
    await load();
  } catch (e) {
    toast(t("error"));
  }
  S.busy = false; render();
}

function Analysing() {
  return h("div", { class: "center" }, h("div", { class: "pulse" }, icon("sparkles", 40)), h("h2", { style: "margin:0" }, t("analysing")), h("div", { class: "muted" }, t("analysingSub")));
}

function Result() {
  const r = S.result, clinic = S.data.clinic;
  return h("div", { class: "result" },
    h("div", { class: "verdict " + r.level }, h("div", { class: "big" }, icon(LEVEL_ICON[r.level], 40)), h("h2", {}, t("level_" + r.level)), h("p", {}, "✓ " + t("sharedWithClinic"))),
    h("section", { class: "card" }, h("span", { class: "pill" }, icon("sparkles", 14), t(r.source === "ai" ? "aiBadge" : "offlineBadge")), h("p", { class: "feedback" }, r.feedback)),
    r.reasons.length ? h("section", { class: "card" }, h("h3", {}, t("whatWeNoticed")),
      h("ul", { class: "reasons" }, r.reasons.map((code) => h("li", {}, h("i", { class: "lv " + S.meta.reasons[code].level }), loc(S.meta.reasons[code].text))))) : null,
    r.level !== "green" ? h("a", { class: "btn" + (r.level === "red" ? " danger" : ""), href: "tel:" + clinic.phone.replace(/\s/g, "") }, icon("phone", 18), t("callClinic")) : null,
    r.level === "red" ? h("a", { class: "btn ghost", href: "tel:103" }, t("call103")) : null,
    h("button", { class: "btn " + (r.level === "green" ? "" : "plain"), onclick: () => { S.result = null; S.tab = "home"; render(); } }, t("home")));
}

// ---- chats -------------------------------------------------------------------

function Chat({ title, icon, intro, messages, mine, placeholder, suggestions, onSend, typing }) {
  const input = h("input", { placeholder, enterkeyhint: "send", onkeydown: (e) => { if (e.key === "Enter") send(); } });
  const send = (text) => { const v = (text || input.value).trim(); if (v && !S.sending) { input.value = ""; onSend(v); } };
  return h("div", { class: "chat" },
    h("div", { class: "page-title" }, h("div", { class: "badge soft" }, window.icon(icon, 20)), title),
    h("div", { class: "msgs" },
      intro ? h("div", { class: "msg them" }, intro) : null,
      !intro && !messages.length ? h("div", { class: "muted", style: "text-align:center;margin-top:40px" }, t("noMessages")) : null,
      messages.map((m) => m.note ? h("div", { class: "msg note " + m.note }, m.text)
        : h("div", { class: "msg " + (m.sender === mine ? "me" : "them") }, m.text, m.created_at ? h("time", {}, fmtTime(m.created_at)) : null)),
      typing ? h("div", { class: "msg them typing" }, h("span"), h("span"), h("span")) : null),
    suggestions && messages.length < 2 ? h("div", { class: "sugs" }, suggestions.map((s) => h("button", { onclick: () => send(s) }, s))) : null,
    h("div", { class: "composer" }, input, h("button", { onclick: () => send(), "aria-label": t("send") }, window.icon("send", 19))));
}

function AiChat() {
  return Chat({
    title: "Ona AI", icon: "sparkles", intro: t("aiIntro"), mine: "patient", typing: S.sending,
    messages: [...S.data.ai_messages, ...(S.pending ? [S.pending] : [])].flatMap((m) => [m, ...S.aiExtra.filter((n) => n.after === m.id)]),
    placeholder: t("aiPlaceholder"), suggestions: [t("sug1"), t("sug2"), t("sug3")],
    onSend: async (text) => {
      S.pending = { sender: "patient", text }; S.sending = true; render();
      try {
        const res = await api("/api/chat", { patient_id: S.pid, lang: S.lang, text });
        await load();
        if (res.escalate !== "none") S.aiExtra.push({ after: S.data.ai_messages.at(-1).id, note: res.escalate, text: t("escalated_" + res.escalate) });
      } catch (e) { toast(t("error")); }
      S.pending = null; S.sending = false; render();
    },
  });
}

function ClinicChat() {
  return Chat({
    title: S.data.patient.doctor, icon: "user", mine: "patient", messages: S.data.clinic_messages, placeholder: t("clinicPlaceholder"),
    onSend: async (text) => {
      try { S.data.clinic_messages = (await api(`/api/patients/${S.pid}/messages`, { sender: "patient", text })).messages; } catch (e) { toast(t("error")); }
      render();
    },
  });
}

// ---- history -----------------------------------------------------------------

function History() {
  const list = S.data.checkins;
  return h("div", {}, h("div", { class: "page-title" }, h("div", { class: "badge soft" }, icon("calendar", 20)), t("tabHistory")),
    h("div", { class: "stack hist" }, list.length ? list.map((c) => {
      const a = c.answers, sym = (a.symptoms || []).filter((s) => s !== "none").map((s) => loc(S.meta.symptoms[s]));
      return h("div", { class: "card" },
        h("div", { class: "row", style: "justify-content:space-between" }, h("b", {}, fmtTime(c.created_at)), h("span", { class: "pill " + c.level }, t("level_" + c.level))),
        h("div", { class: "meta" }, h("span", {}, `${t("mood")}: ${FACES[(a.mood || 3) - 1]}`),
          a.bp ? h("span", {}, `${t("bp")}: ${a.bp.sys}/${a.bp.dia}`) : null, a.weight ? h("span", {}, `${t("weight")}: ${a.weight} kg`) : null,
          sym.length ? h("span", {}, sym.join(", ")) : null));
    }) : h("div", { class: "muted", style: "text-align:center;margin-top:40px" }, t("historyEmpty"))));
}

// ---- boot --------------------------------------------------------------------

(async function boot() {
  try {
    // A mother arrives through her invite link (?k=secret). Remember it, so the home-screen icon opens her own profile.
    let key = params.get("k");
    try { if (key) localStorage.setItem("ona.k", key); else if (!params.get("p")) key = localStorage.getItem("ona.k"); } catch (e) { /* private mode */ }
    if (key) {
      try {
        S.pid = (await api("/api/invite?k=" + encodeURIComponent(key))).patient_id;
      } catch (e) {  // a stale link (for example after a demo reset) must not brick the app
        try { localStorage.removeItem("ona.k"); } catch (e2) { /* ignore */ }
      }
      if (params.get("k")) history.replaceState(null, "", location.pathname);  // keep the secret out of the address bar and screenshots
    }
    [S.meta] = await Promise.all([api("/api/questions"), load()]);
    render();
    // pick up new clinic messages while the app is open
    setInterval(async () => { if (!S.flow && !S.busy && !S.sending && !S.result) { const n = S.data.clinic_messages.length; await load().catch(() => {}); if (S.data.clinic_messages.length !== n) { if (S.tab === "clinic") go("clinic"); else render(); } } }, 5000);
  } catch (e) {
    view.replaceChildren(h("div", { class: "center" }, h("div", { class: "muted" }, String(e.message || e))));
  }
})();
