/* ═══════════════════════════════════════════════════════════════
   SLANJE / LOAD / RESET — glavne chat akcije
   ═══════════════════════════════════════════════════════════════ */

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;

  const voiceTriggers = ["/voice", "start voice", "voice on", "pokreni glas", "slušaj"];
  if (voiceTriggers.includes(text.toLowerCase())) {
    msgInput.value = "";
    toggleRecording();
    return;
  }

  turns++;
  syncStats();
  addMsg(text, "user", false, false);
  msgInput.value = "";
  sendBtn.disabled = true;
  showTyping();

  try {
    const enriched = await enrichWithWeather(text);
    const data = await postJSON("/chat", { message: enriched });
    hideTyping();
    if (data.error) {
      addMsg(data.error, "error", false, false);
    } else {
      addMsg(data.reply, "bot", true, false);
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

async function loadFile() {
  const path = fileInput.value.trim();
  if (!path) return;
  loadBtn.disabled = true;
  try {
    const data = await postJSON("/load", { path: path });
    if (data.error) {
      addMsg(data.error, "error", false, false);
    } else {
      files++; syncStats();
      addMsg("Loaded " + data.filename + " into context.", "system", false, false);
      fileInput.value = "";
    }
  } catch (_) {
    addMsg("Failed to load file.", "error", false, false);
  } finally {
    loadBtn.disabled = false;
    fileInput.focus();
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
  if (e.key === "Enter" && e.shiftKey)  { e.preventDefault(); fileInput.focus(); }
});

fileInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter") { e.preventDefault(); loadFile(); }
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

  if (activeChatId) {
    const data = await getJSON("/api/chats/history?id=" + activeChatId);
    const msgs = (data.messages || []).filter(function(m) { return m.role !== "system"; });
    if (msgs.length > 0) {
      rebuildChat(data.messages);
      turns = data.turn || 0;
      files = (data.loaded_files || []).length;
      syncStats();
    }
  }

  startClock();
  fetchWeather();
  msgInput.focus();
})();
