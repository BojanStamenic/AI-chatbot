/* ═══════════════════════════════════════════════════════════════
   SLANJE / LOAD / RESET — glavne chat akcije
   ═══════════════════════════════════════════════════════════════ */

const HELP_TEXT = `### BojanBot — dostupne komande

**Slash komande**
- \`/help\` — prikaži ovu listu
- \`/voice\` — uključi/isključi glasovni mod (ili \`Alt+V\`)

**Chat prečice**
- \`Enter\` — pošalji poruku
- \`Shift+Enter\` — otvori dijalog za attach file
- Klik na ikonicu spajalice — attach file preko putanje

**Sposobnosti bota (pozovi prirodnim jezikom)**
- 🔍 **Web search** — "latest ...", "ko je pobedio...", "cena ..."
- 🎨 **Generiši sliku** — "napravi sliku ...", "nacrtaj ..."
- 📂 **Učitaj fajl** — "učitaj /path/to/file"
- ❓ **Clarification** — bot pita ako je zahtev nejasan

**Kontrola AngryLynx sajta (iza widget-a)**
- Naslov/tekst: "promeni naslov u ...", "promeni podnaslov", "promeni brend", "promeni footer"
- Dugmad: "promeni dugme u ...", "promeni 'Get Started' u ..."
- Tema: "promeni temu u dark/light/purple/green/red"
- Sekcije: "sakrij/prikaži nav|hero|features|social|cta|footer"
- Features: "obriši sve features", "obriši poslednji feature", "obriši 2. feature", "dodaj feature o ...", "zameni 1. feature sa ..."
- Logotipi: "promeni logotipe u Acme, Globex, Umbrella"
- Reset: "reset sajta"

**Učenje (auto)**
- Kad ispraviš bota ("ne, pogrešno, netačno, izmislio si") on verifikuje preko web-a i pamti tačnu činjenicu za sledeći put.`;

function detectOperationType(text) {
  const lower = text.toLowerCase();
  
  // Image generation patterns
  const imagePatterns = [
    'generate image', 'create image', 'make image', 'draw', 'generiši sliku',
    'napravi sliku', 'nacrtaj', 'generate a picture', 'create a picture'
  ];
  if (imagePatterns.some(p => lower.includes(p))) {
    return { type: 'image', status: '🎨 Generating image...' };
  }
  
  // Web search patterns
  const searchPatterns = [
    'latest', 'current', 'today', 'who won', 'what happened', 'score',
    'news', 'price of', 'najnovije', 'trenutno', 'danas', 'rezultat'
  ];
  if (searchPatterns.some(p => lower.includes(p))) {
    return { type: 'search', status: '🔍 Searching the web...' };
  }
  
  // File loading
  if (lower.includes('load') || lower.includes('read file') || lower.includes('učitaj')) {
    return { type: 'file', status: '📂 Loading file...' };
  }
  
  // Default thinking
  return { type: 'default', status: '💭 Thinking...' };
}

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;

  const voiceTriggers = ["/voice", "start voice", "voice on", "pokreni glas", "slušaj"];
  if (voiceTriggers.includes(text.toLowerCase())) {
    msgInput.value = "";
    toggleRecording();
    return;
  }

  if (text.toLowerCase() === "/help") {
    msgInput.value = "";
    addMsg(text, "user", false, false);
    addMsg(HELP_TEXT, "bot", true, false);
    return;
  }

  turns++;
  syncStats();
  addMsg(text, "user", false, false);
  msgInput.value = "";
  sendBtn.disabled = true;
  
  // Detect operation type and show appropriate status
  const operation = detectOperationType(text);
  showTyping(operation.status);

  try {
    const enriched = await enrichWithWeather(text);
    await streamChat(enriched);
    loadChatList();
  } catch (_) {
    hideTyping();
    addMsg("Network error — could not reach the server.", "error", false, false);
  } finally {
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

async function streamChat(message) {
  const resp = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!resp.ok || !resp.body) {
    hideTyping();
    addMsg("Stream request failed.", "error", false, false);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let botDiv = null;
  let botBody = null;
  let fullText = "";

  function ensureBotMsg() {
    if (botDiv) return;
    hideTyping();
    hideWelcome();
    botDiv = document.createElement("div");
    botDiv.className = "msg bot";
    botDiv.style.animation = "none";
    const label = document.createElement("span");
    label.className = "msg-label";
    label.textContent = "BojanBot";
    botDiv.appendChild(label);
    botBody = document.createElement("div");
    botDiv.appendChild(botBody);
    chatEl.appendChild(botDiv);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const eventBlock = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let data = "";
      for (const line of eventBlock.split("\n")) {
        if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      let payload;
      try { payload = JSON.parse(data); } catch (_) { continue; }

      if (payload.type === "status") {
        updateTypingStatus(payload.text);
      } else if (payload.type === "token") {
        ensureBotMsg();
        fullText += payload.content;
        if (botBody) {
          botBody.innerHTML = renderMarkdown(fullText);
          chatEl.scrollTop = chatEl.scrollHeight;
        }
      } else if (payload.type === "clarification") {
        hideTyping();
        addMsg(payload.content, "bot", true, false);
      } else if (payload.type === "error") {
        hideTyping();
        addMsg(payload.error || "Model request failed.", "error", false, false);
        if (typeof payload.tokens_today === "number") {
          const el = document.getElementById("tokenStat");
          if (el) el.textContent = payload.tokens_today.toLocaleString();
        }
      } else if (payload.type === "done") {
        hideTyping();
        // Apply site-actions on the full text and rerender clean
        if (botBody && typeof applySiteActions === "function") {
          const cleaned = applySiteActions(fullText);
          if (cleaned == null || cleaned === "") {
            if (botDiv) botDiv.remove();
          } else {
            botBody.innerHTML = renderMarkdown(cleaned);
          }
        }
        if (typeof payload.tokens_today === "number") {
          const el = document.getElementById("tokenStat");
          if (el) el.textContent = payload.tokens_today.toLocaleString()
            + (payload.tokens_last_turn ? " (+" + payload.tokens_last_turn + ")" : "");
        }
        if (payload.active_model) {
          const m = document.getElementById("modelStat");
          if (m) {
            const short = payload.active_model.replace("llama-", "").replace("-versatile","").replace("-instant","");
            m.textContent = short;
            m.title = payload.active_model;
            m.style.color = payload.active_model.includes("8b") ? "#ff9a3c" : "";
          }
        }
        if (ttsEnabled && fullText) speak(fullText);
      }
    }
  }
}

async function clearChat() {
  try {
    await postJSON("/reset", {});
    turns = 0; files = 0; syncStats();
    rebuildChat([]);
    loadChatList();
  } catch (_) {
    addMsg("Failed to clear session.", "error", false, false);
  }
}

function askFilePath() {
  return new Promise(function(resolve) {
    const overlay = document.getElementById("fileModal");
    const input   = document.getElementById("filePathModal");
    const okBtn   = document.getElementById("fileModalOk");
    const cancel  = document.getElementById("fileModalCancel");

    function close(val) {
      overlay.hidden = true;
      input.value = "";
      okBtn.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      input.removeEventListener("keydown", onKey);
      overlay.removeEventListener("click", onOverlay);
      resolve(val);
    }
    function onOk()      { close(input.value.trim()); }
    function onCancel()  { close(""); }
    function onKey(e)    {
      if (e.key === "Enter")  { e.preventDefault(); onOk(); }
      if (e.key === "Escape") { e.preventDefault(); onCancel(); }
    }
    function onOverlay(e){ if (e.target === overlay) onCancel(); }

    overlay.hidden = false;
    setTimeout(function(){ input.focus(); }, 20);
    okBtn.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    input.addEventListener("keydown", onKey);
    overlay.addEventListener("click", onOverlay);
  });
}

async function loadFile() {
  const path = (await askFilePath()).trim();
  if (!path) return;
  loadBtn.disabled = true;

  showTyping('📂 Loading file...');

  try {
    const data = await postJSON("/load", { path: path });
    hideTyping();
    if (data.error) {
      addMsg(data.error, "error", false, false);
    } else {
      files++; syncStats();
      addMsg("Loaded " + data.filename + " into context.", "system", false, false);
    }
  } catch (_) {
    hideTyping();
    addMsg("Failed to load file.", "error", false, false);
  } finally {
    loadBtn.disabled = false;
    msgInput.focus();
  }
}


/* ═══════════════════════════════════════════════════════════════
   EVENT LISTENERI — tastatura, dugmad, precice
   ═══════════════════════════════════════════════════════════════ */

sendBtn.addEventListener("click", sendMessage);
clearBtn.addEventListener("click", clearChat);
loadBtn.addEventListener("click", loadFile);

msgInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  if (e.key === "Enter" && e.shiftKey)  { e.preventDefault(); loadFile(); }
});

document.addEventListener("keydown", function(e) {
  if (e.altKey && e.key.toLowerCase() === "v" && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    toggleRecording();
  }
});


/* ═══════════════════════════════════════════════════════════════
   INIT — pokretanje aplikacije
   ═══════════════════════════════════════════════════════════════ */

(async function init() {
  await loadChatList();

  // Start every page load with a fresh, empty chat so we never resume
  // a previous conversation's topic. If the currently-active chat is
  // already empty, reuse it; otherwise create a new one.
  let needNew = true;
  if (activeChatId) {
    const data = await getJSON("/api/chats/history?id=" + activeChatId);
    const msgs = (data.messages || []).filter(function(m) { return m.role !== "system"; });
    if (msgs.length === 0) {
      needNew = false;
    }
  }
  if (needNew) {
    const created = await postJSON("/api/chats/new", {});
    activeChatId = created.id;
    await loadChatList();
  }

  startClock();
  fetchWeather();
  msgInput.focus();
})();
