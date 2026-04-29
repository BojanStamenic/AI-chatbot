/* ═══════════════════════════════════════════════════════════════
   CHAT PORUKE — renderovanje, welcome kartica, typing indikator
   ═══════════════════════════════════════════════════════════════ */

function rebuildChat(messages) {
  chatEl.innerHTML = "";
  let hasMessages = false;
  messages.forEach(function(m) {
    if (m.role === "system") return;
    hasMessages = true;
    if (m.role === "user") {
      addMsg(m.content, "user", false, true);
    } else if (m.role === "assistant") {
      addMsg(m.content, "bot", true, true);
    }
  });
  if (!hasMessages) {
    showWelcome();
  }
}

function showWelcome() {
  const card = document.createElement("div");
  card.className = "welcome";
  card.id = "welcomeCard";
  card.innerHTML =
    '<div class="welcome-icon" style="width:110px;height:110px;">' +
      '<svg viewBox="0 0 24 24" class="robot-svg" style="width:100%;height:100%;">' +
        '<line x1="12" y1="1" x2="12" y2="4" stroke="#fff" stroke-width="1.2" stroke-linecap="round"/>' +
        '<circle cx="12" cy="1.3" r="1" fill="#fe2929"/>' +
        '<rect x="4" y="4" width="16" height="15" rx="3" fill="#fff"/>' +
        '<rect x="2.3" y="9" width="2" height="5" rx="0.5" fill="#fff"/>' +
        '<rect x="19.7" y="9" width="2" height="5" rx="0.5" fill="#fff"/>' +
        '<circle cx="9" cy="11" r="2.2" fill="#0d1017"/>' +
        '<circle cx="15" cy="11" r="2.2" fill="#0d1017"/>' +
        '<circle class="eye" data-cx="9" data-cy="11" cx="9" cy="11" r="1" fill="#ff7a2f"/>' +
        '<circle class="eye" data-cx="15" data-cy="11" cx="15" cy="11" r="1" fill="#ff7a2f"/>' +
        '<rect x="7" y="15" width="10" height="2.4" rx="0.5" fill="#0d1017"/>' +
        '<line x1="9" y1="15.2" x2="9" y2="17.2" stroke="#fff" stroke-width="0.5"/>' +
        '<line x1="11" y1="15.2" x2="11" y2="17.2" stroke="#fff" stroke-width="0.5"/>' +
        '<line x1="13" y1="15.2" x2="13" y2="17.2" stroke="#fff" stroke-width="0.5"/>' +
        '<line x1="15" y1="15.2" x2="15" y2="17.2" stroke="#fff" stroke-width="0.5"/>' +
      '</svg>' +
    '</div>' +
    '<h2>Welcome to <span>BojanBot</span></h2>' +
    '<p>Your AI-powered assistant. Ask anything, generate images from text, get real-time info, or load files for analysis.</p>' +
    '<div class="feature-grid">' +
      '<div class="feature-card"><span class="icon">&#127912;</span><strong>Image Generation</strong><small>Describe any image and get it generated instantly.</small></div>' +
      '<div class="feature-card"><span class="icon">&#127760;</span><strong>Web Search</strong><small>Real-time info from the web, always up to date.</small></div>' +
      '<div class="feature-card"><span class="icon">&#9889;</span><strong>Fast Answers</strong><small>Blazing-fast responses powered by Groq.</small></div>' +
    '</div>';
  chatEl.appendChild(card);
}

function hideWelcome() {
  const wc = document.getElementById("welcomeCard");
  if (wc) {
    wc.style.transition = "opacity 200ms ease, transform 200ms ease";
    wc.style.opacity = "0";
    wc.style.transform = "translateY(-8px)";
    setTimeout(function() { wc.remove(); }, 220);
  }
}

function addMsg(text, type, useMarkdown, noAnim) {
  if (type === "bot" && !noAnim && typeof applySiteActions === "function") {
    text = applySiteActions(text);
    if (!text) return null;
  } else if (type === "bot" && noAnim && typeof applySiteActions === "function") {
    // Rebuilding history — strip tags from display but DO NOT re-execute actions
    text = text.replace(/<site-action>[\s\S]*?<\/site-action>/g, "").trim();
    if (!text) return null;
  }
  hideWelcome();
  const div = document.createElement("div");
  div.className = "msg " + type;
  if (noAnim) div.style.animation = "none";

  if (type === "bot" || type === "user") {
    const label = document.createElement("span");
    label.className = "msg-label";
    label.textContent = type === "user" ? "You" : "BojanBot";
    div.appendChild(label);
  }

  const body = document.createElement("div");
  if (useMarkdown) {
    body.innerHTML = renderMarkdown(text);
  } else {
    body.textContent = text;
  }
  div.appendChild(body);
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function showTyping(statusText) {
  hideWelcome();
  const el = document.createElement("div");
  el.className = "typing"; 
  el.id = "typingIndicator";
  
  // Status text if provided
  if (statusText) {
    const status = document.createElement("div");
    status.className = "typing-status";
    status.textContent = statusText;
    el.appendChild(status);
  }
  
  // Animated dots
  const dots = document.createElement("div");
  dots.className = "typing-dots";
  dots.innerHTML = "<span></span><span></span><span></span>";
  el.appendChild(dots);
  
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function updateTypingStatus(statusText) {
  const el = document.getElementById("typingIndicator");
  if (!el) return;
  
  let statusDiv = el.querySelector(".typing-status");
  if (!statusDiv) {
    statusDiv = document.createElement("div");
    statusDiv.className = "typing-status";
    el.insertBefore(statusDiv, el.firstChild);
  }
  statusDiv.textContent = statusText;
}

function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}
