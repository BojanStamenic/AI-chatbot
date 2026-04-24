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
    
    // If it's likely a search, update status after initial request
    if (operation.type === 'search') {
      setTimeout(() => updateTypingStatus('🔍 Analyzing results...'), 2000);
    }
    
    const data = await postJSON("/chat", { message: enriched });
    hideTyping();
    if (data.error) {
      addMsg(data.error, "error", false, false);
      if (typeof data.tokens_today === "number") {
        const el = document.getElementById("tokenStat");
        if (el) el.textContent = data.tokens_today.toLocaleString();
      }
    } else {
      addMsg(data.reply, "bot", true, false);
      if (typeof data.tokens_today === "number") {
        const el = document.getElementById("tokenStat");
        if (el) el.textContent = data.tokens_today.toLocaleString()
          + (data.tokens_last_turn ? " (+" + data.tokens_last_turn + ")" : "");
      }
      if (data.active_model) {
        const m = document.getElementById("modelStat");
        if (m) {
          const short = data.active_model.replace("llama-", "").replace("-versatile","").replace("-instant","");
          m.textContent = short;
          m.title = data.active_model;
          m.style.color = data.active_model.includes("8b") ? "#ff9a3c" : "";
        }
      }
      if (ttsEnabled) speak(data.reply);
    }
    loadChatList();
  } catch (_) {
    hideTyping();
    addMsg("Network error — could not reach the server.", "error", false, false);
  } finally {
    sendBtn.disabled = false;
    msgInput.focus();
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
