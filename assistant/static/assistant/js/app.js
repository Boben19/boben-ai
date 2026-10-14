/* Boben AI front-end (vanilla JavaScript).
 * Sections: 1) helpers  2) safe text renderer  3) chat UI  4) online/offline  5) PWA install + service worker
 */
(function () {
  "use strict";

  // ---------- Element shortcuts ----------
  const $ = (id) => document.getElementById(id);
  const chatLog = $("chatLog");
  const welcome = $("welcome");
  const form = $("composer");
  const input = $("composer-input");
  const sendBtn = $("sendBtn");
  const counter = $("counter");

  const MAX_CHARS = 2000;
  const HISTORY_SENT = 12;                 // how many past messages we send for context
  const STORAGE_KEY = "boben-chat-v1";

  // The conversation: [{role: "user" | "assistant", text, time}]
  let messages = [];
  let busy = false;

  // ======================================================================
  // 1) Helpers
  // ======================================================================
  function nowLabel(date) {
    return (date || new Date()).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function getCookie(name) {
    const match = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function saveChat() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-60))); } catch (e) { /* storage may be blocked */ }
  }
  function loadChat() {
    try {
      const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (Array.isArray(data)) {
        return data.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.text === "string");
      }
    } catch (e) { /* ignore */ }
    return [];
  }

  function scrollToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  // ======================================================================
  // 2) Safe text renderer
  // We escape ALL HTML first, then add a few simple formats ourselves.
  // That way a reply can never inject scripts into the page.
  // ======================================================================
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function inlineFormat(escaped) {
    return escaped
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  }

  function renderMarkdownLite(text) {
    const parts = text.split(/```/);         // odd-numbered parts are code blocks
    let html = "";
    parts.forEach((part, i) => {
      if (i % 2 === 1) {
        const code = part.replace(/^[^\n]*\n/, ""); // drop the language label line
        html += "<pre><code>" + escapeHtml(code.replace(/\n$/, "")) + "</code></pre>";
        return;
      }
      const lines = escapeHtml(part).split("\n");
      let list = null;                       // "ul" | "ol" | null
      let para = [];
      const flushPara = () => { if (para.length) { html += "<p>" + inlineFormat(para.join("<br>")) + "</p>"; para = []; } };
      const closeList = () => { if (list) { html += "</" + list + ">"; list = null; } };

      lines.forEach((line) => {
        const bullet = line.match(/^\s*[-*•]\s+(.*)/);
        const number = line.match(/^\s*\d+[.)]\s+(.*)/);
        if (bullet || number) {
          flushPara();
          const type = bullet ? "ul" : "ol";
          if (list !== type) { closeList(); html += "<" + type + ">"; list = type; }
          html += "<li>" + inlineFormat((bullet || number)[1]) + "</li>";
        } else if (line.trim() === "") {
          flushPara(); closeList();
        } else {
          closeList(); para.push(line);
        }
      });
      flushPara(); closeList();
    });
    return html;
  }

  // ======================================================================
  // 3) Chat UI
  // ======================================================================
  function hideWelcome() {
    if (welcome) welcome.hidden = true;
  }

  function addMessage(role, text, opts) {
    opts = opts || {};
    hideWelcome();

    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "ai") + (opts.error ? " error" : "");

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.textContent = (role === "user" ? "YOU" : "BOBEN AI 🍀") + " · " + nowLabel(opts.time ? new Date(opts.time) : null);

    const bubble = document.createElement("div");
    bubble.className = "bubble " + (role === "user" ? "" : "bubble-ai");
    if (role === "user") bubble.textContent = text;            // plain text: always safe
    else bubble.innerHTML = renderMarkdownLite(text);          // escaped first, see above

    wrap.appendChild(meta);
    wrap.appendChild(bubble);

    if (role !== "user" && !opts.error) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy-btn";
      copy.textContent = "📋 Copy";
      copy.setAttribute("aria-label", "Copy this response");
      copy.addEventListener("click", () => copyText(text, copy));
      wrap.appendChild(copy);
    }

    chatLog.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function copyText(text, button) {
    const done = () => { button.textContent = "✅ Copied"; setTimeout(() => (button.textContent = "📋 Copy"), 1500); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { /* nothing else we can do */ }
    document.body.removeChild(ta);
  }

  function showTyping() {
    const wrap = document.createElement("div");
    wrap.className = "msg ai";
    wrap.id = "typingRow";
    wrap.innerHTML = '<div class="bubble bubble-ai typing" role="status" aria-label="Boben is typing">' +
                     "<span></span><span></span><span></span></div>";
    chatLog.appendChild(wrap);
    scrollToBottom();
  }
  function hideTyping() {
    const row = $("typingRow");
    if (row) row.remove();
  }

  function setBusy(state) {
    busy = state;
    sendBtn.disabled = state;
    sendBtn.firstChild.textContent = state ? "Thinking… " : "Send ";
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
    const n = input.value.length;
    counter.textContent = n + " / " + MAX_CHARS;
    counter.classList.toggle("warn", n > MAX_CHARS * 0.9);
  }

  async function sendMessage(text) {
    text = (text || "").trim();
    if (!text || busy) return;

    if (text.length > MAX_CHARS) {
      addMessage("assistant", "That message is a bit long. Please keep it under " + MAX_CHARS + " characters.", { error: true });
      return;
    }
    if (!navigator.onLine) {
      addMessage("assistant", "I'm offline right now, so I can't answer new questions. Your message is still in the box. Send it once you're back online. 📡", { error: true });
      return;
    }

    // History = what was said BEFORE this message (trimmed to the last few turns).
    const history = messages
      .slice(-HISTORY_SENT)
      .map((m) => ({ role: m.role, text: m.text }));

    const time = new Date().toISOString();
    messages.push({ role: "user", text: text, time: time });
    addMessage("user", text, { time: time });
    input.value = "";
    autoGrow();
    saveChat();

    setBusy(true);
    showTyping();

    try {
      const res = await fetch(window.BOBEN.chatUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
        body: JSON.stringify({ message: text, history: history }),
      });

      let data = {};
      try { data = await res.json(); } catch (e) { /* not JSON */ }
      hideTyping();

      if (res.ok && data.reply) {
        const replyTime = new Date().toISOString();
        messages.push({ role: "assistant", text: data.reply, time: replyTime });
        addMessage("assistant", data.reply, { time: replyTime });
        saveChat();
      } else if (res.status === 403) {
        addMessage("assistant", "Your session expired. Please refresh the page and try again.", { error: true });
      } else {
        addMessage("assistant", data.error || "Something went wrong on my side. Please try again.", { error: true });
      }
    } catch (err) {
      hideTyping();
      addMessage("assistant", navigator.onLine
        ? "I couldn't reach the server. Is it running? Please try again."
        : "You went offline. Reconnect and send that again. 📡", { error: true });
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  function clearChat() {
    messages = [];
    saveChat();
    chatLog.querySelectorAll(".msg").forEach((el) => el.remove());
    welcome.hidden = false;
    input.focus();
  }

  // ----- Events -----
  form.addEventListener("submit", (e) => { e.preventDefault(); sendMessage(input.value); });

  input.addEventListener("keydown", (e) => {
    // Enter sends; Shift+Enter makes a new line. (isComposing: don't send while typing with an IME.)
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage(input.value);
    }
  });
  input.addEventListener("input", autoGrow);

  document.querySelectorAll("[data-send]").forEach((btn) =>
    btn.addEventListener("click", () => sendMessage(btn.dataset.send)));

  document.querySelectorAll("[data-prompt]").forEach((btn) =>
    btn.addEventListener("click", () => {
      input.value = btn.dataset.prompt;
      autoGrow();
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      closeSidebar();
    }));

  $("clearBtn").addEventListener("click", clearChat);
  $("clearBtnSide").addEventListener("click", () => { clearChat(); closeSidebar(); });

  function closeSidebar() {
    const el = $("sidebar");
    if (window.bootstrap && el.classList.contains("show")) {
      const inst = window.bootstrap.Offcanvas.getInstance(el);
      if (inst) inst.hide();
    }
  }

  // Restore the previous conversation (if any)
  messages = loadChat();
  messages.forEach((m) => addMessage(m.role, m.text, { time: m.time }));
  autoGrow();

  // ======================================================================
  // 4) Online / offline status
  // ======================================================================
  const banner = $("offlineBanner");
  const pill = $("statusPill");
  const pillText = $("statusText");

  function updateOnlineStatus() {
    const online = navigator.onLine;
    banner.hidden = online;
    pill.classList.toggle("online", online);
    pill.classList.toggle("offline", !online);
    pillText.textContent = online ? "Online" : "Offline";
    input.placeholder = online
      ? "Ask Boben anything… (Enter to send, Shift+Enter for a new line)"
      : "You're offline. You can type, but I can only answer when you're back online.";
  }
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);
  updateOnlineStatus();

  // ======================================================================
  // 5) PWA: service worker + install button
  // ======================================================================
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(window.BOBEN.swUrl, { scope: "/" })
        .catch((err) => console.warn("Service worker registration failed:", err));
    });
  }

  let deferredInstall = null;
  const installButtons = [$("installBtn"), $("installBtnSide")];

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();                  // keep the event so OUR button can trigger it
    deferredInstall = e;
    installButtons.forEach((b) => (b.hidden = false));
  });

  installButtons.forEach((b) =>
    b.addEventListener("click", async () => {
      if (!deferredInstall) return;
      deferredInstall.prompt();
      await deferredInstall.userChoice;
      deferredInstall = null;
      installButtons.forEach((x) => (x.hidden = true));
    }));

  window.addEventListener("appinstalled", () => installButtons.forEach((b) => (b.hidden = true)));

  // ======================================================================
  // Floating background emojis (decoration; ignored by screen readers)
  // ======================================================================
  (function makeFloaties() {
    const box = $("floaties");
    const icons = ["🍀", "🌿", "🌱", "✨", "💚", "🌸", "☁️"];
    const count = window.innerWidth < 600 ? 9 : 16;
    for (let i = 0; i < count; i++) {
      const s = document.createElement("span");
      s.className = "floaty";
      s.textContent = icons[i % icons.length];
      s.style.left = Math.round((i / count) * 100 + Math.random() * 4) + "%";
      s.style.fontSize = 18 + Math.round(Math.random() * 22) + "px";
      s.style.animationDuration = 18 + Math.round(Math.random() * 20) + "s";
      s.style.animationDelay = "-" + Math.round(Math.random() * 30) + "s";
      s.style.setProperty("--y", Math.round(Math.random() * 90) + "%");
      box.appendChild(s);
    }
  })();
})();
