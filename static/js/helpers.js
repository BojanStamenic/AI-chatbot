/* ═══════════════════════════════════════════════════════════════
   DOM REFERENCE — svi elementi kojima pristupamo
   ═══════════════════════════════════════════════════════════════ */

const chatEl      = document.getElementById("chat");
const msgInput    = document.getElementById("message");
const sendBtn     = document.getElementById("sendBtn");
const clearBtn    = document.getElementById("clearBtn");
const loadBtn     = document.getElementById("loadBtn");
const turnStat    = document.getElementById("turnStat");
const loadedStat  = document.getElementById("loadedStat");
const chatList    = document.getElementById("chatList");
const newChatBtn  = document.getElementById("newChatBtn");
const headerTitle = document.getElementById("headerTitle");
const sidebar     = document.getElementById("sidebar");
const overlay     = document.getElementById("sidebarOverlay");
const hamburger   = document.getElementById("hamburgerBtn");

let turns = 0;
let files = 0;
let activeChatId = null;


/* ═══════════════════════════════════════════════════════════════
   HELPERI — fetch wrapperi, markdown renderer, formatiranje
   ═══════════════════════════════════════════════════════════════ */

function syncStats() {
  turnStat.textContent  = turns;
  loadedStat.textContent = files;
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  return res.json();
}

async function getJSON(url) {
  const res = await fetch(url);
  return res.json();
}

function renderMarkdown(text) {
  let html = text
    .replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
      return '<pre><code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code></pre>';
    })
    .replace(/`([^`]+)`/g, function(_, code) {
      return '<code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code>';
    })
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" loading="lazy" onclick="window.open(this.src,\'_blank\')">')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');

  const parts = html.split(/(<pre>[\s\S]*?<\/pre>|<img [^>]+>)/g);
  html = parts.map(function(part) {
    if (part.startsWith('<pre>') || part.startsWith('<img')) return part;
    return part.replace(/\n/g, '<br>');
  }).join('');
  return html;
}

function timeAgo(ts) {
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function escHtml(s) {
  var d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
