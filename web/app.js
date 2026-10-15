// Daňko – web UI: chat over SSE, push-to-talk (Web Speech API / server STT), spoken verdicts, law changelog, memory.
(() => {
  "use strict";
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("danko." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("danko." + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  const SUGGESTIONS = [
    "Som na obede s klientom – môžem platiť firemnou kartou?",
    "Potrebujem televízor domov – ako to zaplatiť cez firmu legálne?",
    "Mám si ako konateľ dať odmenu, alebo brať dividendy?",
    "Oplatí sa zamestnať priateľku v mojej s.r.o.?",
    "Čo musím vybaviť pri zakladaní s.r.o. na služby?",
    "Klient je firma z Nemecka – čo s DPH na faktúre?",
  ];

  const state = {
    config: { auth_required: false, stt_server: false, tts_server: false },
    token: store.get("token", ""),
    conversationId: store.get("conversation", null),
    mode: store.get("mode", "quick"),
    lang: store.get("lang", "sk"),
    autoSpeak: store.get("autoSpeak", true),
    busy: false,
    abort: null,
    view: "chat",
  };

  // ------------------------------------------------------------------ API
  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (state.token) headers.Authorization = "Bearer " + state.token;
    if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    if (res.status === 401) { await askToken(); return api(path, opts); }
    return res;
  }
  async function getJSON(path) {
    const res = await api(path);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }
  function askToken() {
    return new Promise((resolve) => {
      const dlg = $("#tokenDialog");
      dlg.addEventListener("close", () => {
        state.token = $("#tokenInput").value.trim();
        store.set("token", state.token);
        resolve();
      }, { once: true });
      dlg.showModal();
    });
  }

  // ------------------------------------------------------------------ helpers
  const fmtTime = (iso) => {
    if (!iso) return "?";
    const d = new Date(iso);
    return d.toLocaleString("sk-SK", { day: "numeric", month: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const skDate = (iso) => {
    if (!iso) return "?";
    const s = String(iso).replace(/-/g, "");
    if (!/^\d{8}$/.test(s)) return iso;
    return `${+s.slice(6)}. ${+s.slice(4, 6)}. ${s.slice(0, 4)}`;
  };
  function splitAnswer(text) {
    const lines = (text || "").split("\n");
    const idx = lines.findIndex((l) => l.trim() === "---");
    if (idx <= 0) return { spoken: "", details: text || "" };
    return { spoken: lines.slice(0, idx).join("\n").trim(), details: lines.slice(idx + 1).join("\n").trim() };
  }
  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  const scrollDown = () => { const m = $("#messages"); m.scrollTop = m.scrollHeight; };

  // ------------------------------------------------------------------ speech output
  let currentAudio = null;
  let currentSayBtn = null;
  function stopSpeaking() {
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (currentSayBtn) currentSayBtn.classList.remove("playing");
    currentSayBtn = null;
  }
  function pickVoice(lang) {
    const voices = (window.speechSynthesis && speechSynthesis.getVoices()) || [];
    const want = lang === "en" ? "en" : "sk";
    return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(want) && /natural|online|enhanced|premium/i.test(v.name))
      || voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(want))
      || (want === "sk" ? voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("cs")) : null);
  }
  async function speak(text, btn) {
    stopSpeaking();
    const plain = MD.toSpeech(text);
    if (!plain) return;
    currentSayBtn = btn || null;
    if (btn) btn.classList.add("playing");
    const done = () => { if (btn) btn.classList.remove("playing"); };
    if (state.config.tts_server) {
      try {
        const res = await api("/api/tts", { method: "POST", json: { text: plain, lang: state.lang } });
        if (res.ok) {
          const url = URL.createObjectURL(await res.blob());
          currentAudio = new Audio(url);
          currentAudio.onended = done;
          await currentAudio.play();
          return;
        }
      } catch { /* fall back to the browser */ }
    }
    if (!window.speechSynthesis) { done(); return; }
    const u = new SpeechSynthesisUtterance(plain);
    u.lang = state.lang === "en" ? "en-US" : "sk-SK";
    const v = pickVoice(state.lang);
    if (v) u.voice = v;
    u.rate = 1.03;
    u.onend = done;
    u.onerror = done;
    speechSynthesis.speak(u);
  }
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};

  // ------------------------------------------------------------------ speech input
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let recorder = null;
  let listening = false;

  function setListening(on) {
    listening = on;
    $("#micBtn").classList.toggle("listening", on);
    $("#hint").textContent = on ? "Počúvam… ťukni znova pre ukončenie" : "Enter = odoslať · Shift+Enter = nový riadok";
  }
  function micAvailable() { return !!SR || (state.config.stt_server && !!navigator.mediaDevices && !!window.MediaRecorder); }

  function startListening() {
    stopSpeaking();
    if (SR) {
      recognition = new SR();
      recognition.lang = state.lang === "en" ? "en-US" : "sk-SK";
      recognition.interimResults = true;
      recognition.continuous = false;
      let finalText = "";
      const input = $("#input");
      const prefix = input.value ? input.value.trim() + " " : "";
      recognition.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
          else interim += e.results[i][0].transcript;
        }
        input.value = prefix + finalText + interim;
        autosize();
      };
      recognition.onerror = (e) => {
        setListening(false);
        if (e.error === "not-allowed") alert("Prístup k mikrofónu bol zamietnutý. Povoľ ho v prehliadači (na telefóne treba HTTPS).");
      };
      recognition.onend = () => {
        setListening(false);
        const text = $("#input").value.trim();
        if (text) send(text, true);
      };
      recognition.start();
      setListening(true);
      return;
    }
    // Fallback: record audio and let the server transcribe it.
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      const chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setListening(false);
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const fd = new FormData();
        fd.append("audio", blob, "voice.webm");
        fd.append("lang", state.lang);
        $("#hint").textContent = "Prepisujem…";
        try {
          const res = await api("/api/stt", { method: "POST", body: fd });
          const data = await res.json();
          if (data.text) send(data.text, true);
        } catch (err) { alert("Prepis zlyhal: " + err.message); }
        $("#hint").textContent = "";
      };
      recorder.start();
      setListening(true);
    }).catch(() => alert("Mikrofón nie je dostupný."));
  }
  function stopListening() {
    if (recognition) { try { recognition.stop(); } catch { /* already stopped */ } }
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  // ------------------------------------------------------------------ chat rendering
  function renderUser(text, voice) {
    $("#welcome").hidden = true;
    const msg = el("div", "msg user");
    const b = el("div", "bubble");
    if (voice) b.appendChild(el("span", "voice-tag", "🎤"));
    b.appendChild(document.createTextNode(text));
    msg.appendChild(b);
    $("#messages").appendChild(msg);
    scrollDown();
  }

  function assistantShell() {
    $("#welcome").hidden = true;
    const msg = el("div", "msg assistant");
    const b = el("div", "bubble");
    const live = el("div", "live-steps");
    const body = el("div", "md");
    body.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
    b.append(live, body);
    msg.appendChild(b);
    $("#messages").appendChild(msg);
    scrollDown();
    return { msg, bubble: b, live, body, steps: [], text: "" };
  }

  function renderAnswer(view, text, meta = {}) {
    const { spoken, details } = splitAnswer(text);
    view.bubble.innerHTML = "";
    if (view.steps.length) {
      const d = el("details", "steps");
      const secs = meta.duration_ms ? ` · ${(meta.duration_ms / 1000).toFixed(0)} s` : "";
      d.appendChild(el("summary", "", `🔍 ${view.steps.length} ${view.steps.length === 1 ? "krok" : view.steps.length < 5 ? "kroky" : "krokov"}${secs}`));
      const ul = el("ul");
      view.steps.forEach((s) => ul.appendChild(el("li", (s.nested ? "nested " : "") + (s.kind === "memory" ? "memory" : ""), MD.esc(s.label))));
      d.appendChild(ul);
      view.bubble.appendChild(d);
    }
    if (spoken) {
      const v = el("div", "verdict");
      const say = el("button", "say", "🔊");
      say.type = "button";
      say.title = "Prečítať nahlas";
      say.onclick = () => (say.classList.contains("playing") ? stopSpeaking() : speak(spoken, say));
      v.append(say, el("div", "verdict-text", MD.inline(spoken).replace(/\n/g, "<br>")));
      view.bubble.appendChild(v);
      view.sayBtn = say;
    }
    view.bubble.appendChild(el("div", "md", MD.render(details || (!spoken ? text : ""))));
    const metaLine = el("div", "meta-line");
    if (meta.memory_saved) metaLine.appendChild(el("span", "mem-saved", "🧠 uložené do pamäte"));
    if (meta.mode === "deep") metaLine.appendChild(el("span", "", "🔬 dôkladný režim"));
    if (metaLine.childNodes.length) view.bubble.appendChild(metaLine);
    return spoken;
  }

  function renderError(view, message) {
    view.bubble.innerHTML = "";
    view.bubble.appendChild(el("div", "error-box", "⚠️ " + MD.esc(message)));
  }

  // ------------------------------------------------------------------ chat flow
  async function send(text, voice = false) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    $("#input").value = "";
    autosize();
    setBusy(true);
    renderUser(text, voice);
    const view = assistantShell();
    const controller = new AbortController();
    state.abort = controller;
    let doneEvent = null;
    try {
      const res = await api("/api/chat", {
        method: "POST",
        json: { message: text, conversation_id: state.conversationId, mode: state.mode, voice, lang: state.lang },
        signal: controller.signal,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          handleEvent(ev, view);
          if (ev.type === "done") doneEvent = ev;
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") renderError(view, err.message);
    } finally {
      setBusy(false);
      state.abort = null;
      loadConversations();
    }
    if (doneEvent) {
      const spoken = renderAnswer(view, doneEvent.text, { ...doneEvent, mode: state.mode });
      view.msg.scrollIntoView({ block: "start", behavior: "smooth" });  // show the verdict first
      if (spoken && (voice || state.autoSpeak)) speak(spoken, view.sayBtn);
      if (doneEvent.memory_saved && state.view === "memory") loadMemory();
    }
  }

  function handleEvent(ev, view) {
    switch (ev.type) {
      case "conversation":
        state.conversationId = ev.id;
        store.set("conversation", ev.id);
        break;
      case "text": {
        view.text += ev.text;
        const { spoken, details } = splitAnswer(view.text);
        view.body.innerHTML = spoken
          ? `<div class="verdict"><div class="verdict-text">${MD.inline(spoken)}</div></div>${MD.render(details)}`
          : MD.render(view.text);
        scrollDown();
        break;
      }
      case "tool": {
        // Text written before a top-level tool call was a preamble ("Pozriem sa…") – start a fresh segment.
        if (!ev.nested) {
          view.text = "";
          view.body.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
        }
        view.steps.push(ev);
        view.live.innerHTML = view.steps.slice(-4).map((s, i, arr) =>
          `<div class="${i === arr.length - 1 ? "cur" : ""}">${s.nested ? "↳ " : ""}${MD.esc(s.label)}</div>`).join("");
        scrollDown();
        break;
      }
      case "error":
        renderError(view, ev.message);
        break;
      default:
        break;
    }
  }

  function setBusy(on) {
    state.busy = on;
    $("#sendBtn").disabled = on;
    $("#micBtn").disabled = on || !micAvailable();
  }

  async function openConversation(id) {
    stopSpeaking();
    const conv = await getJSON(`/api/conversations/${id}`).catch(() => null);
    clearMessages();
    if (!conv) { state.conversationId = null; store.set("conversation", null); return; }
    state.conversationId = conv.id;
    store.set("conversation", conv.id);
    for (const m of conv.messages) {
      if (m.role === "user") renderUser(m.text, m.voice);
      else {
        const view = assistantShell();
        renderAnswer(view, m.text, m);
      }
    }
    highlightConversation();
    closeSidebar();
  }

  function clearMessages() {
    $$("#messages .msg").forEach((n) => n.remove());
    $("#welcome").hidden = false;
  }

  function newConversation() {
    stopSpeaking();
    state.conversationId = null;
    store.set("conversation", null);
    clearMessages();
    highlightConversation();
    closeSidebar();
    switchView("chat");
    $("#input").focus();
  }

  async function loadConversations() {
    let items = [];
    try { items = await getJSON("/api/conversations"); } catch { return; }
    const list = $("#convList");
    list.innerHTML = "";
    if (!items.length) { list.appendChild(el("div", "conv-day", "Zatiaľ žiadne rozhovory")); return; }
    let lastDay = "";
    for (const c of items) {
      const day = new Date(c.updated).toLocaleDateString("sk-SK", { day: "numeric", month: "long" });
      if (day !== lastDay) { list.appendChild(el("div", "conv-day", day)); lastDay = day; }
      const row = el("button", "conv");
      row.dataset.id = c.id;
      row.appendChild(el("span", "conv-title", MD.esc(c.title)));
      const del = el("span", "conv-del", "✕");
      del.title = "Zmazať";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("Zmazať rozhovor?")) return;
        await api(`/api/conversations/${c.id}`, { method: "DELETE" });
        if (state.conversationId === c.id) newConversation();
        loadConversations();
      };
      row.appendChild(del);
      row.onclick = () => openConversation(c.id);
      list.appendChild(row);
    }
    highlightConversation();
  }
  function highlightConversation() {
    $$(".conv").forEach((n) => n.classList.toggle("active", n.dataset.id === state.conversationId));
  }

  // ------------------------------------------------------------------ laws view
  const KIND = {
    baseline: "🆕 Začiatok sledovania",
    upcoming: "⏳ Pripravovaná zmena",
    upcoming_revised: "✏️ Pripravovaná zmena upravená",
    in_force: "✅ Nové znenie účinné",
    effective: "📅 Zmena nadobudla účinnosť",
    news: "📰 Novinka z webu",
  };
  let jobTimer = null;

  async function loadLaws() {
    let status, changelog;
    try {
      [status, changelog] = await Promise.all([getJSON("/api/laws/status"), getJSON("/api/laws/changelog")]);
    } catch (err) {
      $("#lawUpdated").textContent = "Nepodarilo sa načítať: " + err.message;
      return;
    }
    $("#lawUpdated").textContent = status.updated
      ? `Posledná kontrola: ${fmtTime(status.updated)}${status.last_news_check ? ` · novinky: ${fmtTime(status.last_news_check)}` : ""}`
      : "Zákony ešte neboli stiahnuté – spusti kontrolu (prvý beh trvá pár minút).";

    const grid = $("#lawGrid");
    grid.innerHTML = "";
    for (const law of status.laws.filter((l) => l.enabled)) {
      const card = el("div", "law");
      const tags = [];
      if (law.current) tags.push(`<span class="tag ok">účinné od ${skDate(law.current)}</span>`);
      else tags.push('<span class="tag">nestiahnuté</span>');
      (law.upcoming || []).forEach((d) => tags.push(`<span class="tag up">⏳ od ${skDate(d)}</span>`));
      if (law.last_error) tags.push(`<span class="tag err" title="${MD.esc(law.last_error)}">chyba sync</span>`);
      card.innerHTML = `<div class="law-top"><div class="law-name">${MD.esc(law.name)}</div><div class="law-ref">${MD.esc(law.ref)}</div></div>
        <div>${tags.join("")}</div>
        <div class="law-line">${law.last_checked ? "kontrola " + fmtTime(law.last_checked) : ""}</div>`;
      grid.appendChild(card);
    }

    const seen = store.get("seenChangelog", []);
    const tl = $("#timeline");
    tl.innerHTML = "";
    if (!changelog.length) tl.appendChild(el("div", "empty", "Zatiaľ žiadne zmeny. Po prvej kontrole tu uvidíš, čo sa v zákonoch zmenilo a čo to znamená pre tvoju s.r.o."));
    for (const e of changelog) tl.appendChild(renderEntry(e, !seen.includes(e.id)));
    store.set("seenChangelog", changelog.map((e) => e.id));
    updateBadge(0);
    renderJob(status.job);
  }

  function renderEntry(e, unread) {
    const a = e.analysis || {};
    const sev = a.severity || e.severity || "";
    const card = el("article", `entry ${sev ? "sev-" + sev : ""} ${unread ? "unread" : ""}`);
    const title = e.kind === "news" ? MD.esc(e.title || "") : `${MD.esc(e.law_name)} <span class="muted">(${MD.esc(e.law_ref || "")})</span>`;
    let html = `<div class="entry-head"><span class="entry-kind">${KIND[e.kind] || e.kind}</span><span class="entry-law">${title}</span>
      <span class="entry-date">zistené ${fmtTime(e.detected_at)}</span></div>`;
    const facts = [];
    if (e.effective_from) facts.push(`<span>📅 účinné od <b>${skDate(e.effective_from)}</b></span>`);
    if (e.status) facts.push(`<span>stav: ${MD.esc(e.status)}</span>`);
    if (e.amendments && e.amendments.length) facts.push(`<span>novely: ${MD.esc(e.amendments.join(", "))}</span>`);
    if (e.changed_sections && e.changed_sections.length) {
      const s = e.changed_sections;
      facts.push(`<span>zmenené: ${MD.esc(s.slice(0, 12).join(", "))}${s.length > 12 ? ` … +${s.length - 12}` : ""}</span>`);
    }
    if (e.stats) facts.push(`<span>+${e.stats.added} / −${e.stats.removed} riadkov</span>`);
    if (sev) facts.push(`<span>dôležitosť: <b>${MD.esc(sev)}</b></span>`);
    if (facts.length) html += `<div class="facts">${facts.join("")}</div>`;
    const summary = a.summary || e.summary;
    if (summary) html += `<p>${MD.inline(summary)}</p>`;
    if (a.impact_for_sro && a.impact_for_sro.length) html += `<ul>${a.impact_for_sro.map((x) => `<li>${MD.inline(x)}</li>`).join("")}</ul>`;
    if (a.action_items && a.action_items.length) html += `<p><b>Čo urobiť:</b></p><ul>${a.action_items.map((x) => `<li>☐ ${MD.inline(x)}</li>`).join("")}</ul>`;
    if (e.knowledge_updates && e.knowledge_updates.length) html += `<p class="muted">🧠 Aktualizované znalosti: ${e.knowledge_updates.map((p) => `<code>${MD.esc(p)}</code>`).join(" ")}</p>`;
    if (e.analysis_error) html += `<p class="muted">Analýza zlyhala: ${MD.esc(e.analysis_error)}</p>`;
    if (e.kind === "baseline") html += `<p class="muted">Znenie stiahnuté – poradca ho odteraz používa pri odpovediach.</p>`;
    if (e.url) html += `<p><a href="${MD.esc(e.url)}" target="_blank" rel="noopener">Zdroj ↗</a></p>`;
    card.innerHTML = html;
    return card;
  }

  function renderJob(job) {
    const box = $("#jobStatus");
    const btn = $("#syncBtn");
    if (job && job.running) {
      box.hidden = false;
      box.textContent = `⏳ Kontrola beží od ${fmtTime(job.started)} – sťahujem znenia zo Slov-Lex${$("#syncAnalyze").checked ? " a analyzujem zmeny" : ""}…`;
      btn.disabled = true;
      clearTimeout(jobTimer);
      jobTimer = setTimeout(loadLaws, 5000);
    } else {
      btn.disabled = false;
      if (job && job.finished) {
        box.hidden = false;
        const r = job.result || {};
        const errs = r.errors ? Object.keys(r.errors) : [];
        box.textContent = job.error
          ? `⚠️ Kontrola zlyhala: ${job.error}`
          : `✔️ Hotovo (${fmtTime(job.finished)}): ${r.summary || ""}${r.analyzed ? ` · analyzované: ${r.analyzed}` : ""}${r.news ? ` · novinky: ${r.news}` : ""}${errs.length ? ` · chyby: ${errs.join(", ")}` : ""}`;
      } else box.hidden = true;
    }
  }

  async function startSync() {
    const res = await api("/api/laws/sync", {
      method: "POST",
      json: { analyze: $("#syncAnalyze").checked, news: $("#syncNews").checked },
    });
    const data = await res.json();
    renderJob(data.job);
  }

  async function refreshBadge() {
    try {
      const changelog = await getJSON("/api/laws/changelog?limit=50");
      const seen = store.get("seenChangelog", null);
      if (seen === null) { store.set("seenChangelog", changelog.filter((e) => e.kind === "baseline").map((e) => e.id)); }
      const unread = changelog.filter((e) => e.kind !== "baseline" && !(store.get("seenChangelog", [])).includes(e.id)).length;
      updateBadge(unread);
    } catch { /* ignore */ }
  }
  function updateBadge(n) {
    const b = $("#lawBadge");
    b.hidden = !n;
    b.textContent = n > 9 ? "9+" : String(n);
  }

  // ------------------------------------------------------------------ memory view
  async function loadMemory() {
    try {
      const m = await getJSON("/api/memory");
      $("#memMemory").innerHTML = MD.render(m.memory.replace(/<!--[\s\S]*?-->/g, "")) || "<p class='muted'>Prázdne</p>";
      $("#memCompany").innerHTML = MD.render(m.company.replace(/<!--[\s\S]*?-->/g, "")) || "<p class='muted'>Prázdne</p>";
    } catch (err) {
      $("#memMemory").textContent = "Nepodarilo sa načítať: " + err.message;
    }
  }

  // ------------------------------------------------------------------ UI wiring
  function switchView(view) {
    state.view = view;
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
    $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
    if (view === "laws") loadLaws();
    if (view === "memory") loadMemory();
  }
  function autosize() {
    const t = $("#input");
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 180) + "px";
  }
  function openSidebar() { $("#sidebar").classList.add("open"); $("#scrim").classList.add("show"); }
  function closeSidebar() { $("#sidebar").classList.remove("open"); $("#scrim").classList.remove("show"); }

  function applyPrefs() {
    $("#langBtn").textContent = state.lang.toUpperCase();
    $("#speakBtn").setAttribute("aria-pressed", String(state.autoSpeak));
    $("#speakBtn").textContent = state.autoSpeak ? "🔊" : "🔇";
    $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === state.mode));
    $("#input").placeholder = state.lang === "en" ? "Ask anything or tap 🎤" : "Napíš otázku alebo ťukni na 🎤";
  }

  function wire() {
    const chips = $("#chips");
    SUGGESTIONS.forEach((s) => {
      const c = el("button", "chip", MD.esc(s));
      c.type = "button";
      c.onclick = () => send(s);
      chips.appendChild(c);
    });
    $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send($("#input").value); });
    $("#input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($("#input").value); }
    });
    $("#input").addEventListener("input", autosize);
    $("#micBtn").addEventListener("click", () => (listening ? stopListening() : startListening()));
    $$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
    $$(".mode-btn").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; store.set("mode", state.mode); applyPrefs(); }));
    $("#langBtn").addEventListener("click", () => { state.lang = state.lang === "sk" ? "en" : "sk"; store.set("lang", state.lang); applyPrefs(); });
    $("#speakBtn").addEventListener("click", () => {
      state.autoSpeak = !state.autoSpeak;
      store.set("autoSpeak", state.autoSpeak);
      if (!state.autoSpeak) stopSpeaking();
      applyPrefs();
    });
    $("#newChat").addEventListener("click", newConversation);
    $("#openSidebar").addEventListener("click", openSidebar);
    $("#closeSidebar").addEventListener("click", closeSidebar);
    $("#scrim").addEventListener("click", closeSidebar);
    $("#syncBtn").addEventListener("click", startSync);
    $("#memRefresh").addEventListener("click", loadMemory);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") stopSpeaking(); });
  }

  async function init() {
    wire();
    applyPrefs();
    try { state.config = await getJSON("/api/config"); } catch { /* server down – shown in footer */ }
    if (state.config.auth_required && !state.token) await askToken();
    $("#micBtn").disabled = !micAvailable();
    if (!micAvailable()) $("#micBtn").title = "Tento prehliadač nepodporuje rozpoznávanie reči (skús Chrome/Safari alebo nastav STT_PROVIDER).";
    try {
      const h = await getJSON("/api/health");
      $("#healthInfo").innerHTML = h.claude_found
        ? `<span class="dot"></span>Claude Code pripojený · v${MD.esc(h.version)}`
        : `<span class="dot bad"></span>Claude CLI nenájdené – nainštaluj Claude Code`;
    } catch { $("#healthInfo").innerHTML = '<span class="dot bad"></span>Server nedostupný'; }
    await loadConversations();
    if (state.conversationId) await openConversation(state.conversationId);
    refreshBadge();
  }

  init();
})();
