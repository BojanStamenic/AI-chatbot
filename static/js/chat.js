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
    '<div class="welcome-icon">' +
      '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/></svg>' +
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
