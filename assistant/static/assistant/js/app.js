/* Boben front-end (vanilla JavaScript).
 * Sections: 1) setup + storage  2) theme + settings  3) safe text renderer  4) chats list
 *           5) messages  6) sending  7) composer, voice, shortcuts  8) online/offline  9) PWA
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const chatLog = $("chatLog"), chatInner = $("chatInner"), welcome = $("welcome");
  const form = $("composer"), input = $("composer-input"), sendBtn = $("sendBtn"), micBtn = $("micBtn");
  const titleInput = $("titleInput"), chatList = $("chatList");

  const MAX_CHARS = 2000, HISTORY_SENT = 12, MAX_CHATS = 30, MAX_MSGS = 80;
  // Chats and saved answers are kept per account, so two people on one device never see each other's chats.
  const UID = String((window.BOBEN && window.BOBEN.userId) || "guest");
  const LEGACY_STORE_KEY = "boben-chats-v2", LEGACY_SAVED_KEY = "boben-saved-v1";
  const STORE_KEY = LEGACY_STORE_KEY + ":" + UID, PREFS_KEY = "boben-prefs-v1", OLD_KEY = "boben-chat-v1";
  const PLACEHOLDERS = {
    chat: "Message Boben",
    study: "What are you studying?",
    code: "Paste your code or describe the bug",
    write: "What are you writing?",
    plan: "What do you need to get done?",
  };

  let busy = false, abortCtl = null, searchTerm = "";

  // ======================================================================
  // 1) Setup + storage (everything stays in this browser)
  // ======================================================================
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (e) { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage may be blocked */ }
  }
  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  // First sign-in after this update: the account takes over the chats that were saved before accounts existed.
  try {
    [[LEGACY_STORE_KEY, STORE_KEY], [LEGACY_SAVED_KEY, LEGACY_SAVED_KEY + ":" + UID]].forEach(function (pair) {
      if (localStorage.getItem(pair[0]) && !localStorage.getItem(pair[1])) {
        localStorage.setItem(pair[1], localStorage.getItem(pair[0]));
        localStorage.removeItem(pair[0]);
      }
    });
  } catch (e) { /* storage may be blocked */ }

  let prefs = Object.assign({ name: "", theme: "auto", length: "balanced", mode: "chat", size: "medium", fun: "on", hinted: false }, read(PREFS_KEY, {}));
  let store = loadStore();

  function loadStore() {
    const saved = read(STORE_KEY, null);
    if (saved && Array.isArray(saved.chats)) return saved;
    // First run after the redesign: bring over the old single conversation, if there was one.
    const old = read(OLD_KEY, []);
    const chats = [];
    if (Array.isArray(old) && old.length) {
      const firstUser = old.find((m) => m.role === "user");
      chats.push({ id: uid(), title: shorten(firstUser ? firstUser.text : "Earlier chat"), updated: Date.now(), messages: old });
    }
    return { chats: chats, currentId: chats.length ? chats[0].id : null };
  }
  function saveStore() {
    store.chats = store.chats.filter((c) => c.messages.length || c.id === store.currentId).slice(0, MAX_CHATS);
    store.chats.forEach((c) => { c.messages = c.messages.slice(-MAX_MSGS); });
    write(STORE_KEY, store);
  }
  function shorten(text) {
    const t = (text || "").replace(/\s+/g, " ").trim();
    return t.length > 40 ? t.slice(0, 40).trim() + "…" : t || "New chat";
  }
  const current = () => store.chats.find((c) => c.id === store.currentId);

  function newChat() {
    const empty = store.chats.find((c) => !c.messages.length);   // reuse an empty chat instead of piling them up
    if (empty) { store.currentId = empty.id; } else {
      const chat = { id: uid(), title: "New chat", updated: Date.now(), messages: [] };
      store.chats.unshift(chat);
      store.currentId = chat.id;
    }
    saveStore(); renderAll(); input.focus();
  }

  // ======================================================================
  // 2) Theme + settings + toasts
  // ======================================================================
  const dark = matchMedia("(prefers-color-scheme: dark)");
  function applyTheme() {
    const isDark = prefs.theme === "dark" || (prefs.theme === "auto" && dark.matches);
    root.dataset.theme = isDark ? "dark" : "light";
    root.setAttribute("data-bs-theme", isDark ? "dark" : "light");
    $("themeColor").setAttribute("content", isDark ? "#090d0b" : "#eaf1ed");
  }
  dark.addEventListener("change", applyTheme);

  function syncSegments() {
    document.querySelectorAll(".seg").forEach((seg) => {
      const key = seg.dataset.setting;
      seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(prefs[key] === b.dataset.value)));
    });
  }
  document.querySelectorAll(".seg button").forEach((b) =>
    b.addEventListener("click", () => {
      prefs[b.closest(".seg").dataset.setting] = b.dataset.value;
      write(PREFS_KEY, prefs); applyTheme(); applySize(); applyFun(); syncSegments();
    }));
  $("settingsBtn").addEventListener("click", () => {
    closeSidebar();
    window.bootstrap.Modal.getOrCreateInstance($("settingsModal")).show();
  });
  $("clearAllBtn").addEventListener("click", () => {
    if (!confirm("Delete all your chats on this device? This can't be undone.")) return;
    store = { chats: [], currentId: null };
    newChat();
    window.bootstrap.Modal.getOrCreateInstance($("settingsModal")).hide();
    toast("All chats deleted");
  });

  function toast(message, action) {
    const pill = document.createElement("div");
    pill.className = "toast-pill";
    const span = document.createElement("span");
    span.textContent = message;
    pill.appendChild(span);
    if (action) {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = action.label;
      b.addEventListener("click", () => { action.run(); pill.remove(); });
      pill.appendChild(b);
    }
    $("toastHost").appendChild(pill);
    setTimeout(() => pill.remove(), action ? 6000 : 2200);
  }

  // ======================================================================
  // 3) Safe text renderer: escape ALL HTML first, then add simple formats ourselves
  // ======================================================================
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function inlineFormat(escaped) {
    return escaped
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  }
  function renderMarkdownLite(text) {
    const parts = text.split(/```/);                       // odd-numbered parts are code blocks
    let html = "";
    parts.forEach((part, i) => {
      if (i % 2 === 1) {
        const lang = (part.match(/^[^\n]*/)[0] || "").trim().replace(/[^\w+#.-]/g, "").slice(0, 20);
        const code = part.replace(/^[^\n]*\n/, "").replace(/\n$/, "");
        html += '<div class="codeblock"><div class="code-head"><span>' + (lang || "code") +
                '</span><button type="button" class="code-copy">Copy</button></div><pre><code>' + escapeHtml(code) + "</code></pre></div>";
        return;
      }
      let list = null, para = [];
      const flushPara = () => { if (para.length) { html += "<p>" + inlineFormat(para.join("<br>")) + "</p>"; para = []; } };
      const closeList = () => { if (list) { html += "</" + list + ">"; list = null; } };
      escapeHtml(part).split("\n").forEach((line) => {
        const bullet = line.match(/^\s*[-*•]\s+(.*)/), number = line.match(/^\s*\d+[.)]\s+(.*)/), head = line.match(/^#{1,4}\s+(.*)/);
        if (head) { flushPara(); closeList(); html += '<p class="md-h">' + inlineFormat(head[1]) + "</p>"; }
        else if (bullet || number) {
          flushPara();
          const type = bullet ? "ul" : "ol";
          if (list !== type) { closeList(); html += "<" + type + ">"; list = type; }
          html += "<li>" + inlineFormat((bullet || number)[1]) + "</li>";
        } else if (line.trim() === "") { flushPara(); closeList(); }
        else { closeList(); para.push(line); }
      });
      flushPara(); closeList();
    });
    return html;
  }
  function plainText(md) {
    return md.replace(/```[\s\S]*?```/g, " code block ").replace(/[*`#]/g, "");
  }

  // ======================================================================
  // 4) Chats list (sidebar) + header
  // ======================================================================
  function relTime(ts) {
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return mins + " min ago";
    const d = new Date(ts), today = new Date();
    if (d.toDateString() === today.toDateString()) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const y = new Date(today); y.setDate(today.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  function renderList() {
    chatList.replaceChildren();
    const chats = store.chats
      .filter((c) => c.messages.length && (!searchTerm || c.title.toLowerCase().includes(searchTerm) ||
                     c.messages.some((m) => m.text.toLowerCase().includes(searchTerm))))
      .sort((a, b) => b.updated - a.updated);
    if (!chats.length) {
      const p = document.createElement("p");
      p.className = "chat-empty"; p.textContent = searchTerm ? "No chats match that." : "Your chats will show up here.";
      chatList.appendChild(p);
      return;
    }
    chats.forEach((c) => {
      const row = document.createElement("div");
      row.className = "chat-item" + (c.id === store.currentId ? " active" : "");
      const open = document.createElement("button");
      open.type = "button"; open.className = "chat-open";
      if (c.id === store.currentId) open.setAttribute("aria-current", "true");
      const t = document.createElement("strong"); t.textContent = c.title;
      const s = document.createElement("span"); s.textContent = relTime(c.updated);
      open.append(t, s);
      open.addEventListener("click", () => { store.currentId = c.id; saveStore(); renderAll(); closeSidebar(); });
      const del = document.createElement("button");
      del.type = "button"; del.className = "icon-btn chat-del";
      del.setAttribute("aria-label", "Delete chat " + c.title);
      del.innerHTML = '<svg class="ic" aria-hidden="true"><use href="#i-trash"/></svg>';
      del.addEventListener("click", () => deleteChat(c.id));
      row.append(open, del);
      chatList.appendChild(row);
    });
  }

  function deleteChat(id) {
    const index = store.chats.findIndex((c) => c.id === id);
    if (index < 0) return;
    const removed = store.chats.splice(index, 1)[0];
    if (store.currentId === id) store.currentId = null;
    if (!store.chats.length || !store.currentId) {
      const next = store.chats.find((c) => c.messages.length);
      if (next) store.currentId = next.id; else { newChat(); }
    }
    saveStore(); renderAll();
    toast("Chat deleted", { label: "Undo", run: () => {
      store.chats.splice(Math.min(index, store.chats.length), 0, removed);
      store.currentId = removed.id; saveStore(); renderAll();
    } });
  }

  function commitTitle() {
    const chat = current();
    const value = titleInput.value.trim();
    if (!chat) return;
    chat.title = value || shorten((chat.messages.find((m) => m.role === "user") || {}).text);
    titleInput.value = chat.title;
    saveStore(); renderList();
  }
  titleInput.addEventListener("blur", commitTitle);
  titleInput.addEventListener("keydown", (e) => { if (e.key === "Enter") titleInput.blur(); });

  // ======================================================================
  // 5) Messages
  // ======================================================================
  const timeLabel = (iso) => (iso ? new Date(iso) : new Date()).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const scrollToBottom = () => { chatLog.scrollTop = chatLog.scrollHeight; };

  function actBtn(label, icon, text, cls) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "act " + (cls || ""); b.title = label;
    b.setAttribute("aria-label", label);
    b.innerHTML = '<svg class="ic" aria-hidden="true"><use href="#' + icon + '"/></svg>' + (text ? "<span>" + text + "</span>" : "");
    return b;
  }

  function addMessage(m) {
    welcome.hidden = true;
    const isUser = m.role === "user";
    if (!isUser && !m.error && !m.id) m.id = uid();
    const wrap = document.createElement("div");
    wrap.className = "msg " + (isUser ? "user" : "ai") + (m.error ? " error" : "");

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (isUser) bubble.textContent = m.text;                    // plain text is always safe
    else if (m.error) bubble.textContent = m.text;
    else bubble.innerHTML = renderMarkdownLite(m.text);         // escaped first, see above
    wrap.appendChild(bubble);

    if (m.error && m.retry) {
      const r = document.createElement("button");
      r.type = "button"; r.className = "retry-inline"; r.textContent = "Try again";
      r.addEventListener("click", () => { wrap.remove(); respond(); });
      bubble.appendChild(r);
    }

    if (!m.error) {
      const meta = document.createElement("div");
      meta.className = "msg-meta";
      meta.textContent = (isUser ? "" : "Boben · ") + timeLabel(m.time);
      wrap.appendChild(meta);
    }

    if (!isUser && !m.error) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const copy = actBtn("Copy reply", "i-copy", "Copy");
      copy.addEventListener("click", () => copyText(m.text, () => toast("Copied")));
      actions.appendChild(copy);

      const star = actBtn(isSaved(m.id) ? "Remove from saved" : "Save this answer", "i-star", "");
      star.classList.toggle("on", isSaved(m.id));
      star.addEventListener("click", () => {
        const nowSaved = toggleSaved(m);
        star.classList.toggle("on", nowSaved);
        star.setAttribute("aria-label", nowSaved ? "Remove from saved" : "Save this answer");
        star.title = star.getAttribute("aria-label");
        if (nowSaved) { const r = star.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, ["⭐", "✨"], 8, 60); toast("Saved"); }
      });
      actions.appendChild(star);

      const heart = document.createElement("button");
      heart.type = "button"; heart.className = "act act-emoji"; heart.title = "Love this answer";
      heart.setAttribute("aria-label", "Love this answer"); heart.setAttribute("aria-pressed", String(!!m.liked));
      heart.textContent = m.liked ? "❤️" : "🤍";
      heart.addEventListener("click", () => {
        m.liked = !m.liked; saveStore();
        heart.textContent = m.liked ? "❤️" : "🤍"; heart.setAttribute("aria-pressed", String(m.liked));
        if (m.liked) { const r = heart.getBoundingClientRect(); burst(r.left + r.width / 2, r.top + r.height / 2, ["❤️", "💚", "✨"], 9, 70); }
      });
      actions.appendChild(heart);
      if ("speechSynthesis" in window) {
        const say = actBtn("Read aloud", "i-speaker", "");
        say.addEventListener("click", () => speak(m.text));
        actions.appendChild(say);
      }
      const retry = actBtn("Write a new reply", "i-retry", "", "act-retry");
      retry.addEventListener("click", regenerate);
      actions.appendChild(retry);
      wrap.appendChild(actions);
    }

    chatInner.appendChild(wrap);
    refreshLast();
    scrollToBottom();
    return wrap;
  }

  function refreshLast() {
    chatInner.querySelectorAll(".msg.is-last").forEach((el) => el.classList.remove("is-last"));
    const all = chatInner.querySelectorAll(".msg.ai:not(.error):not(#typingRow)");
    if (all.length) all[all.length - 1].classList.add("is-last");
    refreshFollowups();
  }

  function copyText(text, done) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else fallbackCopy(text, done);
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { /* nothing else we can do */ }
    document.body.removeChild(ta);
  }
  chatInner.addEventListener("click", (e) => {                  // "Copy" buttons on code blocks
    const btn = e.target.closest(".code-copy");
    if (!btn) return;
    const code = btn.closest(".codeblock").querySelector("code").textContent;
    copyText(code, () => { btn.textContent = "Copied"; setTimeout(() => (btn.textContent = "Copy"), 1400); });
  });

  function speak(text) {
    const synth = window.speechSynthesis;
    if (synth.speaking) { synth.cancel(); return; }
    synth.speak(new SpeechSynthesisUtterance(plainText(text)));
  }

  function showTyping() {
    const wrap = document.createElement("div");
    wrap.className = "msg ai"; wrap.id = "typingRow";
    wrap.innerHTML = '<div class="bubble typing" role="status" aria-label="Boben is replying"><span></span><span></span><span></span></div>';
    chatInner.appendChild(wrap); scrollToBottom();
  }
  const hideTyping = () => { const r = $("typingRow"); if (r) r.remove(); };

  function greeting() {
    const h = new Date().getHours();
    const part = h < 5 ? "Up late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    const first = ((window.BOBEN && window.BOBEN.name) || prefs.name || "").trim().split(/\s+/)[0];
    return first ? part + ", " + first : part;
  }
  const renderGreeting = () => { $("greetTitle").textContent = greeting() + " \u{1F44B}"; };

  function renderChat() {
    chatInner.querySelectorAll(".msg").forEach((el) => el.remove());
    const chat = current();
    titleInput.value = chat ? chat.title : "New chat";
    welcome.hidden = !!(chat && chat.messages.length);
    renderGreeting();
    if (chat) chat.messages.forEach(addMessage);
    scrollToBottom();
  }
  function renderAll() { renderList(); renderChat(); updateSend(); }

  // ======================================================================
  // 6) Sending messages
  // ======================================================================
  async function sendMessage(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    if (text.length > MAX_CHARS) { toast("Keep it under " + MAX_CHARS + " characters"); return; }
    if (!navigator.onLine) { toast("You're offline. Your message is safe in the box."); return; }

    const chat = current();
    const msg = { role: "user", text: text, time: new Date().toISOString() };
    chat.messages.push(msg);
    if (chat.messages.length === 1) { chat.title = shorten(text); titleInput.value = chat.title; }
    chat.updated = Date.now();
    addMessage(msg);
    input.value = ""; autoGrow();
    saveStore(); renderList();
    respond();
  }

  /* Ask the server for a reply to the last message in the current chat. */
  async function respond() {
    const chat = current();
    const last = chat.messages[chat.messages.length - 1];
    if (!last || last.role !== "user") return;

    const history = chat.messages.slice(-1 - HISTORY_SENT, -1).map((m) => ({ role: m.role, text: m.text }));
    setBusy(true); showTyping();
    abortCtl = new AbortController();

    try {
      const res = await fetch(window.BOBEN.chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
        signal: abortCtl.signal,
        body: JSON.stringify({ message: last.text, history: history, mode: prefs.mode, length: prefs.length }),
      });
      let data = {};
      try { data = await res.json(); } catch (e) { /* not JSON */ }
      hideTyping();

      if (res.ok && data.reply) {
        const reply = { role: "assistant", text: data.reply, time: new Date().toISOString() };
        chat.messages.push(reply); chat.updated = Date.now();
        addMessage(reply); saveStore(); renderList();
      } else if (res.status === 401) {
        addMessage({ role: "assistant", error: true, text: "Your session ended. Please sign in again to keep chatting." });
        toast("Session ended", { label: "Sign in", run: () => { location.href = window.BOBEN.loginUrl + "?next=/"; } });
      } else if (res.status === 403) {
        addMessage({ role: "assistant", error: true, retry: true, text: "Your session expired. Refresh the page, then try again." });
      } else {
        addMessage({ role: "assistant", error: true, retry: true, text: data.error || "Something went wrong on my side." });
      }
    } catch (err) {
      hideTyping();
      if (err && err.name === "AbortError") { toast("Stopped", { label: "Retry", run: respond }); return; }
      addMessage({ role: "assistant", error: true, retry: true, text: navigator.onLine
        ? "I couldn't reach the server. Is it running?"
        : "You went offline. Reconnect, then try again." });
    } finally {
      setBusy(false); refreshFollowups();
      if (matchMedia("(pointer: fine)").matches) input.focus();   // on phones, don't pop the keyboard back up
    }
  }

  function regenerate() {
    if (busy) return;
    const chat = current();
    while (chat.messages.length && chat.messages[chat.messages.length - 1].role === "assistant") chat.messages.pop();
    saveStore();
    const all = chatInner.querySelectorAll(".msg.ai");
    if (all.length) all[all.length - 1].remove();
    refreshLast();
    respond();
  }

  function getCookie(name) {
    const match = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }
  function setBusy(state) { busy = state; updateSend(); }

  // ----- Save a chat as a text file -----
  $("exportBtn").addEventListener("click", () => {
    const chat = current();
    if (!chat || !chat.messages.length) { toast("Nothing to save yet"); return; }
    const lines = chat.messages.map((m) => (m.role === "user" ? "You" : "Boben") + " (" + timeLabel(m.time) + ")\n" + m.text);
    const blob = new Blob([chat.title + "\n\n" + lines.join("\n\n")], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (chat.title.replace(/[^\w\- ]+/g, "").trim() || "chat") + ".txt";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast("Chat saved");
  });

  // ======================================================================
  // 7) Composer, modes, voice, shortcuts
  // ======================================================================
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
    const n = input.value.length, counter = $("counter");
    counter.hidden = n < MAX_CHARS * 0.8;
    counter.textContent = n + " / " + MAX_CHARS;
    counter.classList.toggle("warn", n > MAX_CHARS * 0.95);
    updateSend();
  }
  let sendShowsStop = null;
  function updateSend() {
    sendBtn.disabled = !busy && !input.value.trim();
    if (sendShowsStop === busy) return;
    sendShowsStop = busy;
    sendBtn.classList.toggle("stop", busy);
    sendBtn.setAttribute("aria-label", busy ? "Stop replying" : "Send message");
    sendBtn.innerHTML = '<svg class="ic" aria-hidden="true"><use href="#' + (busy ? "i-stop" : "i-up") + '"/></svg>';
  }

  function setMode(mode) {
    prefs.mode = PLACEHOLDERS[mode] ? mode : "chat";
    write(PREFS_KEY, prefs);
    document.querySelectorAll("#modeRow .chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.mode === prefs.mode)));
    input.placeholder = navigator.onLine ? PLACEHOLDERS[prefs.mode] : "Offline. You can type, but replies need a connection.";
  }
  document.querySelectorAll("#modeRow .chip").forEach((c) => c.addEventListener("click", () => { setMode(c.dataset.mode); input.focus(); }));

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) { if (abortCtl) abortCtl.abort(); return; }     // the send button turns into a stop button
    sendMessage(input.value);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(input.value); }
  });
  input.addEventListener("input", autoGrow);

  document.querySelectorAll("[data-send]").forEach((b) => b.addEventListener("click", () => sendMessage(b.dataset.send)));
  document.querySelectorAll(".mode-card").forEach((b) =>
    b.addEventListener("click", () => {
      setMode(b.dataset.mode);
      input.value = b.dataset.starter; autoGrow(); input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }));

  $("newChatBtn").addEventListener("click", () => { newChat(); closeSidebar(); });
  $("newChatTop").addEventListener("click", newChat);
  document.addEventListener("keydown", (e) => {                 // Ctrl/Cmd + K starts a new chat
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); newChat(); }
  });

  function closeSidebar() {
    const el = $("sidebar");
    if (window.bootstrap && el.classList.contains("show")) {
      const inst = window.bootstrap.Offcanvas.getInstance(el);
      if (inst) inst.hide();
    }
  }

  // ----- Dictation (only where the browser supports it) -----
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Recognition) {
    micBtn.hidden = false;
    let rec = null, base = "";
    micBtn.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new Recognition();
      rec.interimResults = true; rec.lang = navigator.language || "en-US";
      base = input.value ? input.value.trim() + " " : "";
      rec.onresult = (e) => {
        let said = "";
        for (let i = 0; i < e.results.length; i++) said += e.results[i][0].transcript;
        input.value = (base + said).slice(0, MAX_CHARS); autoGrow();
      };
      rec.onend = () => { rec = null; micBtn.classList.remove("listening"); micBtn.setAttribute("aria-label", "Dictate a message"); };
      rec.onerror = () => toast("I couldn't hear that. Check your mic permission.");
      rec.start();
      micBtn.classList.add("listening"); micBtn.setAttribute("aria-label", "Stop dictating");
    });
  }

  // ======================================================================
  // 8) Online / offline
  // ======================================================================
  let wasOffline = !navigator.onLine;
  function updateOnlineStatus() {
    const online = navigator.onLine;
    $("offlineBanner").hidden = online;
    $("netPill").hidden = online;
    setMode(prefs.mode);
    if (online && wasOffline) toast("Back online");
    wasOffline = !online;
  }
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);

  // ======================================================================
  // 9) PWA: service worker + install button (with an iPhone hint)
  // ======================================================================
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(window.BOBEN.swUrl, { scope: "/" })
        .catch((err) => console.warn("Service worker registration failed:", err));
    });
  }

  const installBtn = $("installBtn");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  let deferredInstall = null;

  if (isIOS && !standalone) installBtn.hidden = false;           // Safari has no install prompt, so we explain it
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredInstall = e; installBtn.hidden = false; });
  installBtn.addEventListener("click", async () => {
    if (deferredInstall) {
      deferredInstall.prompt();
      await deferredInstall.userChoice;
      deferredInstall = null; installBtn.hidden = true;
    } else if (isIOS) {
      closeSidebar();
      toast("Tap the Share button, then Add to Home Screen");
    }
  });
  window.addEventListener("appinstalled", () => { installBtn.hidden = true; });


  // ======================================================================
  // 10) Follow-up chips, saved answers, search, About
  // ======================================================================
  const FOLLOWUPS = {
    chat:  ["Explain simpler", "Give an example", "Summarize in 3 bullets", "Go deeper"],
    study: ["Quiz me on this", "Explain simpler", "Make flashcards", "Give an example"],
    code:  ["Explain line by line", "What could go wrong?", "Show a simpler version", "Add comments"],
    write: ["Make it shorter", "More formal", "More casual", "Fix grammar only"],
    plan:  ["Make it more realistic", "Break it into daily steps", "What should I do first?", "Add short breaks"],
  };
  function refreshFollowups() {
    const old = $("followups"); if (old) old.remove();
    const chat = current();
    if (busy || !chat || !chat.messages.length) return;
    if (chat.messages[chat.messages.length - 1].role !== "assistant") return;
    const last = chatInner.lastElementChild;
    if (!last || !last.classList.contains("msg")) return;
    const row = document.createElement("div");
    row.className = "followups"; row.id = "followups";
    (FOLLOWUPS[prefs.mode] || FOLLOWUPS.chat).forEach((label) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "followup"; b.textContent = label;
      b.addEventListener("click", () => sendMessage(label));
      row.appendChild(b);
    });
    chatInner.appendChild(row); scrollToBottom();
  }

  const SAVED_KEY = LEGACY_SAVED_KEY + ":" + UID;
  let saved = read(SAVED_KEY, []);
  if (!Array.isArray(saved)) saved = [];
  const isSaved = (id) => saved.some((s) => s.id === id);
  function toggleSaved(m) {
    if (isSaved(m.id)) saved = saved.filter((s) => s.id !== m.id);
    else saved.push({ id: m.id, text: m.text, chat: (current() || {}).title || "Chat", time: m.time || new Date().toISOString() });
    saved = saved.slice(-100);
    write(SAVED_KEY, saved); updateSavedCount();
    return isSaved(m.id);
  }
  function updateSavedCount() {
    const badge = $("savedCount");
    badge.hidden = !saved.length; badge.textContent = saved.length;
  }
  function renderSaved() {
    const box = $("savedList"); box.replaceChildren();
    if (!saved.length) {
      const p = document.createElement("p");
      p.className = "chat-empty"; p.textContent = "Tap the star on any reply to keep it here.";
      box.appendChild(p); return;
    }
    saved.slice().reverse().forEach((item) => {
      const card = document.createElement("div");
      card.className = "saved-item";
      const body = document.createElement("div");
      body.className = "bubble"; body.innerHTML = renderMarkdownLite(item.text);
      const meta = document.createElement("div");
      meta.className = "msg-meta"; meta.textContent = item.chat + " · " + relTime(Date.parse(item.time) || Date.now());
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const copy = actBtn("Copy", "i-copy", "Copy");
      copy.addEventListener("click", () => copyText(item.text, () => toast("Copied")));
      const del = actBtn("Remove", "i-trash", "Remove");
      del.addEventListener("click", () => {
        saved = saved.filter((s) => s.id !== item.id);
        write(SAVED_KEY, saved); updateSavedCount(); renderSaved(); renderChat();
      });
      actions.append(copy, del);
      card.append(body, meta, actions);
      box.appendChild(card);
    });
  }
  function openModal(id) {
    closeSidebar();
    window.bootstrap.Modal.getOrCreateInstance($(id)).show();
  }
  $("savedBtn").addEventListener("click", () => { renderSaved(); openModal("savedModal"); });
  $("aboutBtn").addEventListener("click", () => openModal("aboutModal"));
  $("searchInput").addEventListener("input", (e) => { searchTerm = e.target.value.trim().toLowerCase(); renderList(); });

  // ======================================================================
  // 11) Focus timer (survives a page reload)
  // ======================================================================
  const TIMER_KEY = "boben-timer-v1", KINDS = { focus: 25, short: 5, long: 15 };
  let timer = Object.assign({ kind: "focus", left: 1500, endsAt: 0, running: false, goal: "", day: "", done: 0 }, read(TIMER_KEY, {}));
  if (!KINDS[timer.kind]) timer.kind = "focus";
  const mmss = (s) => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  const timerTotal = () => KINDS[timer.kind] * 60;
  const saveTimer = () => write(TIMER_KEY, timer);

  function renderTimer() {
    const today = new Date().toDateString();
    if (timer.day !== today) { timer.day = today; timer.done = 0; }
    const s = timer.running ? Math.max(0, Math.ceil((timer.endsAt - Date.now()) / 1000)) : timer.left;
    $("ringTime").textContent = mmss(s);
    $("ringFg").style.strokeDashoffset = String(339.29 * (1 - s / timerTotal()));
    $("timerStart").textContent = timer.running ? "Pause" : (timer.left < timerTotal() ? "Resume" : "Start");
    document.querySelectorAll("#timerModes button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === timer.kind)));
    const badge = $("timerBadge"); badge.hidden = !timer.running; badge.textContent = mmss(s);
    document.title = timer.running ? mmss(s) + " · Boben" : "Boben";
    $("timerSessions").textContent = "Focus sessions today: " + timer.done;
    $("goalInput").value = $("goalInput") === document.activeElement ? $("goalInput").value : timer.goal;
  }
  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.28].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain(), at = ctx.currentTime + t;
        o.frequency.value = 880; g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(0.2, at + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.22);
        o.connect(g); g.connect(ctx.destination); o.start(at); o.stop(at + 0.24);
      });
    } catch (e) { /* sound is optional */ }
  }
  function finishTimer() {
    const wasFocus = timer.kind === "focus";
    timer.running = false; timer.left = timerTotal();
    if (wasFocus) timer.done++;
    saveTimer(); renderTimer(); beep(); rain(["🎉", "✨", "🍀", "💚"]);
    if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
    toast(wasFocus ? "Focus session done. Take a break!" : "Break's over. Ready when you are.");
  }
  setInterval(() => {
    if (!timer.running) return;
    if (Date.now() >= timer.endsAt) finishTimer(); else renderTimer();
  }, 500);

  $("timerBtn").addEventListener("click", () => { renderTimer(); openModal("timerModal"); });
  $("timerStart").addEventListener("click", () => {
    if (timer.running) { timer.left = Math.max(1, Math.ceil((timer.endsAt - Date.now()) / 1000)); timer.running = false; }
    else { timer.endsAt = Date.now() + timer.left * 1000; timer.running = true; }
    saveTimer(); renderTimer();
  });
  $("timerReset").addEventListener("click", () => { timer.running = false; timer.left = timerTotal(); saveTimer(); renderTimer(); });
  document.querySelectorAll("#timerModes button").forEach((b) =>
    b.addEventListener("click", () => { timer.kind = b.dataset.kind; timer.running = false; timer.left = timerTotal(); saveTimer(); renderTimer(); }));
  $("goalInput").addEventListener("input", (e) => { timer.goal = e.target.value.slice(0, 80); saveTimer(); });

  // ======================================================================
  // 12) Effects: emoji bursts, and the background emoji switch
  // ======================================================================
  const layer = $("floaties");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

  function applySize() { root.setAttribute("data-size", prefs.size || "medium"); }

  /* Little emojis fly out from a point and fade away. */
  function burst(x, y, chars, count, spread) {
    if (reduceMotion.matches) return;
    for (let i = 0; i < count; i++) {
      const s = document.createElement("span");
      s.className = "spark"; s.textContent = chars[i % chars.length];
      s.style.left = x + "px"; s.style.top = y + "px"; s.style.fontSize = (14 + Math.random() * 14) + "px";
      layer.appendChild(s);
      const a = Math.random() * Math.PI * 2, d = (spread || 70) * (0.5 + Math.random());
      const dx = Math.cos(a) * d, dy = Math.sin(a) * d - 24;
      s.animate([
        { transform: "translate(-50%, -50%) scale(0.4)", opacity: 1 },
        { transform: "translate(calc(-50% + " + dx + "px), calc(-50% + " + (dy + 34) + "px)) rotate(" + (Math.random() * 140 - 70) + "deg) scale(1)", opacity: 0 },
      ], { duration: 650 + Math.random() * 450, easing: "cubic-bezier(.2,.7,.3,1)" }).onfinish = () => s.remove();
    }
  }
  /* A shower of emojis from the top of the screen (used when a timer finishes). */
  function rain(chars) {
    if (reduceMotion.matches) return;
    for (let i = 0; i < 26; i++) {
      const s = document.createElement("span");
      s.className = "spark"; s.textContent = chars[i % chars.length];
      s.style.left = Math.random() * innerWidth + "px"; s.style.top = "-30px"; s.style.fontSize = (18 + Math.random() * 16) + "px";
      layer.appendChild(s);
      s.animate([{ transform: "translateY(0) rotate(0deg)", opacity: 1 }, { transform: "translateY(" + (innerHeight + 60) + "px) rotate(" + (Math.random() * 360 - 180) + "deg)", opacity: 0.9 }],
        { duration: 1600 + Math.random() * 1600, delay: Math.random() * 500, easing: "cubic-bezier(.4,0,.8,.6)", fill: "backwards" }).onfinish = () => s.remove();
    }
  }

  /* Drifting emojis live in the page background (emoji-bg.js). This only switches them on or off. */
  function applyFun() {
    root.dataset.fun = prefs.fun === "off" ? "off" : "on";
    if (window.BobenEmojiBg) window.BobenEmojiBg.refresh();
  }

  // ======================================================================
  // Start
  // ======================================================================
  applyTheme(); applySize(); syncSegments();
  if (!store.chats.length || !current()) {
    if (store.chats.length) store.currentId = store.chats[0].id; else newChat();
  }
  if (new URLSearchParams(location.search).get("new") === "1") {   // from the app-icon shortcut
    const c = current();
    if (c && c.messages.length) newChat();
    history.replaceState(null, "", location.pathname);
  }
  setMode(prefs.mode);
  renderAll(); autoGrow(); updateOnlineStatus();
  applyFun(); updateSavedCount(); renderTimer();
  console.info("Boben, developed by Jhon Grover Longsud");
})();
