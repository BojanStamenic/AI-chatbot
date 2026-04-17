import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from chatbot import BojanBot, SYSTEM_PROMPT

HOST = "127.0.0.1"
PORT = 8080
STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chats.json")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("Missing GROQ_API_KEY. Add it to .env or export it before starting the UI.")

bot = BojanBot(api_key=api_key)


# ═══════════════════════════════════════════════════════════════
#  CHAT MANAGER — multi-chat with JSON persistence
# ═══════════════════════════════════════════════════════════════

class ChatManager:
    def __init__(self, bot_instance, store_path=STORE_PATH):
        self.bot = bot_instance
        self.store_path = store_path
        self.chats = {}
        self.active_id = None
        self._load()
        if not self.chats:
            self.new_chat()

    # ── persistence ──────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r") as f:
                data = json.load(f)
            self.chats = data.get("chats", {})
            self.active_id = data.get("active")
            if self.active_id and self.active_id in self.chats:
                self._apply_chat(self.active_id)
            elif self.chats:
                first = next(iter(self.chats))
                self._apply_chat(first)
        except (json.JSONDecodeError, KeyError):
            self.chats = {}
            self.active_id = None

    def _save(self):
        self._snapshot_current()
        data = {"active": self.active_id, "chats": self.chats}
        with open(self.store_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── internal helpers ─────────────────────────────────────

    def _snapshot_current(self):
        if self.active_id and self.active_id in self.chats:
            chat = self.chats[self.active_id]
            chat["history"] = self.bot.history
            chat["turn"] = self.bot.turn
            chat["loaded_files"] = self.bot.loaded_files

    def _apply_chat(self, chat_id):
        chat = self.chats[chat_id]
        self.bot.history = chat["history"]
        self.bot.turn = chat["turn"]
        self.bot.loaded_files = chat.get("loaded_files", [])
        self.active_id = chat_id

    # ── public API ───────────────────────────────────────────

    def new_chat(self):
        chat_id = uuid.uuid4().hex[:12]
        self._snapshot_current()
        self.chats[chat_id] = {
            "id": chat_id,
            "title": "New chat",
            "created": time.time(),
            "turn": 0,
            "loaded_files": [],
            "history": [{"role": "system", "content": SYSTEM_PROMPT}],
        }
        self.bot.history = self.chats[chat_id]["history"]
        self.bot.turn = 0
        self.bot.loaded_files = []
        self.active_id = chat_id
        self._save()
        return chat_id

    def switch(self, chat_id):
        if chat_id not in self.chats:
            return False
        self._snapshot_current()
        self._apply_chat(chat_id)
        self._save()
        return True

    def delete(self, chat_id):
        if chat_id not in self.chats:
            return False
        del self.chats[chat_id]
        if self.active_id == chat_id:
            if self.chats:
                first = next(iter(self.chats))
                self._apply_chat(first)
            else:
                self.new_chat()
                return True
        self._save()
        return True

    def rename(self, chat_id, title):
        if chat_id not in self.chats:
            return False
        self.chats[chat_id]["title"] = title[:80]
        self._save()
        return True

    def auto_title(self, chat_id, first_message):
        """Set title from first user message if still default."""
        if chat_id in self.chats and self.chats[chat_id]["title"] == "New chat":
            title = first_message[:50].strip()
            if len(first_message) > 50:
                title += "..."
            self.chats[chat_id]["title"] = title
            self._save()

    def list_chats(self):
        result = []
        for cid, c in self.chats.items():
            result.append({
                "id": c["id"],
                "title": c["title"],
                "created": c["created"],
                "turn": c["turn"],
                "active": cid == self.active_id,
            })
        result.sort(key=lambda x: x["created"], reverse=True)
        return result

    def save_after_message(self):
        self._save()


manager = ChatManager(bot)


# ═══════════════════════════════════════════════════════════════
#  HTML / CSS / JS
# ═══════════════════════════════════════════════════════════════

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>BojanBot — AngryLynx AI</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
  <style>
    /* ═══════════════════════════════════════════
       TOKENS
       ═══════════════════════════════════════════ */
    :root {
      --bg-deep:       #06080d;
      --bg-surface:    #0c1017;
      --bg-card:       #111722;
      --bg-elevated:   #161d2b;
      --bg-input:      #0f1520;
      --bg-sidebar:    #090c12;

      --accent:        #ef7f1a;
      --accent-hover:  #ff9a3c;
      --accent-glow:   rgba(239, 127, 26, 0.35);
      --accent-subtle: rgba(239, 127, 26, 0.08);

      --text-primary:  #e8ecf4;
      --text-secondary:#8c95a8;
      --text-muted:    #555f73;
      --text-inverse:  #06080d;

      --border:        rgba(255, 255, 255, 0.06);
      --border-accent: rgba(239, 127, 26, 0.25);

      --user-bg:       rgba(239, 127, 26, 0.08);
      --user-border:   rgba(239, 127, 26, 0.22);
      --bot-bg:        rgba(99, 145, 255, 0.06);
      --bot-border:    rgba(99, 145, 255, 0.15);
      --system-bg:     rgba(255, 255, 255, 0.03);
      --error-bg:      rgba(239, 68, 68, 0.08);
      --error-border:  rgba(239, 68, 68, 0.25);
      --error-text:    #f87171;
      --success:       #34d399;

      --font-sans:     'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      --font-mono:     'JetBrains Mono', 'Fira Code', monospace;

      --radius-sm:     8px;
      --radius-md:     12px;
      --radius-lg:     16px;
      --radius-xl:     20px;
      --radius-full:   9999px;

      --shadow-sm:     0 2px 8px rgba(0,0,0,0.3);
      --shadow-md:     0 8px 30px rgba(0,0,0,0.4);
      --shadow-lg:     0 20px 60px rgba(0,0,0,0.5);
      --shadow-glow:   0 0 40px var(--accent-glow);

      --sidebar-w:     280px;
    }

    /* ═══════════════════════════════════════════
       RESET
       ═══════════════════════════════════════════ */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 16px; -webkit-font-smoothing: antialiased; }
    body {
      height: 100vh;
      display: flex;
      font-family: var(--font-sans);
      color: var(--text-primary);
      background: var(--bg-deep);
      overflow: hidden;
    }

    /* ═══════════════════════════════════════════
       BG EFFECTS
       ═══════════════════════════════════════════ */
    body::before {
      content: '';
      position: fixed; inset: 0;
      background:
        radial-gradient(ellipse 800px 600px at 20% 10%, rgba(239,127,26,0.06) 0%, transparent 60%),
        radial-gradient(ellipse 600px 500px at 80% 90%, rgba(59,130,246,0.04) 0%, transparent 60%);
      animation: bgPulse 8s ease-in-out infinite alternate;
      pointer-events: none; z-index: 0;
    }
    @keyframes bgPulse {
      0%   { opacity: 0.6; }
      100% { opacity: 1; }
    }
    body::after {
      content: '';
      position: fixed; inset: 0;
      background-image:
        linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px);
      background-size: 60px 60px;
      pointer-events: none; z-index: 0;
    }

    /* ═══════════════════════════════════════════
       LAYOUT: SIDEBAR + MAIN
       ═══════════════════════════════════════════ */
    .layout {
      display: flex;
      width: 100%;
      height: 100%;
      position: relative;
      z-index: 1;
    }

    /* ═══════════════════════════════════════════
       SIDEBAR
       ═══════════════════════════════════════════ */
    .sidebar {
      width: var(--sidebar-w);
      min-width: var(--sidebar-w);
      height: 100%;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 10;
    }

    .sidebar-header {
      padding: 16px;
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .sidebar-brand .lynx-icon {
      width: 36px; height: 36px;
      border-radius: var(--radius-sm);
      background: linear-gradient(135deg, var(--accent), #d66908);
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 3px 12px var(--accent-glow);
      flex-shrink: 0;
    }

    .sidebar-brand .lynx-icon svg { width: 20px; height: 20px; fill: #fff; }

    .sidebar-brand h1 {
      font-size: 16px; font-weight: 800; letter-spacing: -0.3px;
    }
    .sidebar-brand h1 span {
      background: linear-gradient(135deg, var(--accent), var(--accent-hover));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .btn-new-chat {
      width: 100%;
      padding: 10px 14px;
      border-radius: var(--radius-md);
      border: 1px dashed var(--border-accent);
      background: var(--accent-subtle);
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      font-family: var(--font-sans);
      cursor: pointer;
      transition: all 180ms ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .btn-new-chat:hover {
      background: rgba(239, 127, 26, 0.15);
      border-color: var(--accent);
      box-shadow: 0 0 20px rgba(239,127,26,0.1);
    }

    .chat-list {
      flex: 1;
      overflow-y: auto;
      padding: 8px;
    }

    .chat-list::-webkit-scrollbar { width: 4px; }
    .chat-list::-webkit-scrollbar-track { background: transparent; }
    .chat-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 2px; }

    .chat-item {
      padding: 10px 12px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: all 150ms ease;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 2px;
      border: 1px solid transparent;
      position: relative;
    }

    .chat-item:hover {
      background: var(--bg-card);
    }

    .chat-item.active {
      background: var(--bg-elevated);
      border-color: var(--border-accent);
    }

    .chat-item-info {
      flex: 1;
      min-width: 0;
    }

    .chat-item-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.3;
    }

    .chat-item.active .chat-item-title {
      color: var(--accent);
    }

    .chat-item-meta {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    .chat-item-actions {
      display: flex;
      gap: 2px;
      opacity: 0;
      transition: opacity 150ms ease;
      flex-shrink: 0;
    }

    .chat-item:hover .chat-item-actions {
      opacity: 1;
    }

    .chat-item-btn {
      width: 26px; height: 26px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      border-radius: 6px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: all 120ms ease;
    }

    .chat-item-btn:hover {
      background: rgba(255,255,255,0.08);
      color: var(--text-primary);
    }

    .chat-item-btn.delete:hover {
      background: var(--error-bg);
      color: var(--error-text);
    }

    .chat-item-btn svg { width: 14px; height: 14px; }

    .sidebar-footer {
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      font-size: 11px;
      color: var(--text-muted);
      text-align: center;
    }

    /* ═══════════════════════════════════════════
       MAIN PANEL
       ═══════════════════════════════════════════ */
    .main {
      flex: 1;
      height: 100%;
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-width: 0;
      background: var(--bg-surface);
    }

    /* header */
    .header {
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(17,23,34,0.9), var(--bg-surface));
      backdrop-filter: blur(16px);
    }

    .header-left {
      display: flex; align-items: center; gap: 12px;
    }

    .hamburger {
      display: none;
      width: 36px; height: 36px;
      border: 1px solid var(--border);
      background: var(--bg-card);
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
      cursor: pointer;
      align-items: center; justify-content: center;
    }

    .hamburger svg { width: 18px; height: 18px; }

    .header-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 500px;
    }

    .header-right {
      display: flex; align-items: center; gap: 10px;
    }

    .status-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px rgba(52,211,153,0.5);
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%      { opacity: 0.4; }
    }

    .status-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }

    /* ═══════════════════════════════════════════
       BUTTONS
       ═══════════════════════════════════════════ */
    .btn {
      border: 1px solid var(--border);
      background: var(--bg-elevated);
      color: var(--text-secondary);
      border-radius: var(--radius-sm);
      padding: 8px 14px;
      font-size: 13px; font-weight: 600;
      font-family: var(--font-sans);
      cursor: pointer;
      transition: all 180ms ease;
      display: inline-flex; align-items: center; gap: 6px;
      white-space: nowrap;
    }

    .btn:hover {
      background: var(--bg-card); color: var(--text-primary);
      border-color: rgba(255,255,255,0.12);
      transform: translateY(-1px); box-shadow: var(--shadow-sm);
    }
    .btn:active { transform: translateY(0); }
    .btn:disabled {
      opacity: 0.4; cursor: not-allowed;
      transform: none !important; box-shadow: none !important;
    }

    .btn-accent {
      background: linear-gradient(135deg, var(--accent), #d66908);
      border-color: transparent; color: #fff; font-weight: 700;
      box-shadow: 0 4px 14px var(--accent-glow);
    }
    .btn-accent:hover {
      background: linear-gradient(135deg, var(--accent-hover), var(--accent));
      color: #fff; box-shadow: 0 6px 24px var(--accent-glow);
    }

    .btn-ghost {
      background: transparent; border-color: transparent;
      color: var(--text-muted); padding: 8px 10px;
    }
    .btn-ghost:hover {
      background: var(--accent-subtle); color: var(--accent);
      border-color: transparent;
    }

    /* ═══════════════════════════════════════════
       CHAT AREA
       ═══════════════════════════════════════════ */
    #chat {
      padding: 20px 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-deep) 100%);
    }

    #chat::-webkit-scrollbar { width: 6px; }
    #chat::-webkit-scrollbar-track { background: transparent; }
    #chat::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }

    /* welcome */
    .welcome {
      display: flex; flex-direction: column; align-items: center;
      text-align: center; padding: 48px 20px 30px; gap: 20px;
      animation: fadeUp 600ms ease-out;
    }

    .welcome-icon {
      width: 72px; height: 72px; border-radius: 20px;
      background: linear-gradient(135deg, var(--accent), #d66908);
      display: flex; align-items: center; justify-content: center;
      box-shadow: var(--shadow-glow);
      position: relative;
    }
    .welcome-icon::before {
      content: ''; position: absolute; inset: -3px;
      border-radius: 23px;
      background: linear-gradient(135deg, var(--accent), transparent, var(--accent));
      opacity: 0.3; animation: spin 4s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .welcome-icon svg {
      width: 38px; height: 38px; fill: #fff; position: relative; z-index: 1;
    }

    .welcome h2 { font-size: 22px; font-weight: 800; letter-spacing: -0.3px; }
    .welcome h2 span {
      background: linear-gradient(135deg, var(--accent), var(--accent-hover));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .welcome p {
      font-size: 14px; color: var(--text-secondary);
      max-width: 480px; line-height: 1.6;
    }

    .feature-grid {
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 12px; width: 100%; max-width: 640px;
    }
    .feature-card {
      background: var(--bg-card); border: 1px solid var(--border);
      border-radius: var(--radius-md); padding: 16px 14px;
      text-align: left; transition: all 200ms ease; cursor: default;
    }
    .feature-card:hover {
      border-color: var(--border-accent); background: var(--bg-elevated);
      transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .feature-card .icon { font-size: 20px; margin-bottom: 8px; display: block; }
    .feature-card strong {
      font-size: 13px; font-weight: 700; display: block; margin-bottom: 4px;
    }
    .feature-card small { font-size: 11px; color: var(--text-muted); line-height: 1.45; }

    /* ═══════════════════════════════════════════
       MESSAGES
       ═══════════════════════════════════════════ */
    .msg {
      max-width: 80%;
      border-radius: var(--radius-md);
      padding: 12px 16px;
      line-height: 1.55; font-size: 14px;
      animation: msgIn 250ms cubic-bezier(0.16, 1, 0.3, 1);
      word-wrap: break-word;
    }

    .msg pre {
      background: rgba(0,0,0,0.3); border: 1px solid var(--border);
      border-radius: var(--radius-sm); padding: 10px 12px;
      margin: 8px 0 4px; overflow-x: auto;
      font-family: var(--font-mono); font-size: 13px; line-height: 1.5;
    }
    .msg code {
      font-family: var(--font-mono); font-size: 13px;
      background: rgba(0,0,0,0.25); padding: 2px 6px; border-radius: 4px;
    }
    .msg pre code { background: none; padding: 0; }

    @keyframes msgIn {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    .msg.user {
      align-self: flex-end;
      background: var(--user-bg); border: 1px solid var(--user-border);
    }
    .msg.bot {
      align-self: flex-start;
      background: var(--bot-bg); border: 1px solid var(--bot-border);
    }
    .msg.system {
      align-self: center;
      background: var(--system-bg); border: 1px solid var(--border);
      color: var(--text-secondary); font-size: 12px; padding: 8px 14px;
    }
    .msg.error {
      align-self: center;
      background: var(--error-bg); border: 1px solid var(--error-border);
      color: var(--error-text); font-size: 12px; padding: 8px 14px;
    }

    .msg-label {
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 4px; display: block;
    }
    .msg.user .msg-label { color: var(--accent); }
    .msg.bot  .msg-label { color: #6391ff; }

    /* typing */
    .typing {
      align-self: flex-start; display: flex; gap: 5px;
      padding: 14px 18px; background: var(--bot-bg);
      border: 1px solid var(--bot-border); border-radius: var(--radius-md);
      animation: msgIn 250ms ease-out;
    }
    .typing span {
      width: 7px; height: 7px; border-radius: 50%;
      background: #6391ff; animation: typeDot 1.2s ease-in-out infinite;
    }
    .typing span:nth-child(2) { animation-delay: 0.15s; }
    .typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes typeDot {
      0%, 60%, 100% { opacity: 0.25; transform: scale(0.85); }
      30%           { opacity: 1;    transform: scale(1.1); }
    }

    /* ═══════════════════════════════════════════
       BOTTOM PANEL
       ═══════════════════════════════════════════ */
    .bottom {
      border-top: 1px solid var(--border);
      padding: 14px 24px;
      background: var(--bg-surface);
      display: flex; flex-direction: column; gap: 10px;
    }

    .chips { display: flex; gap: 8px; flex-wrap: wrap; }

    .chip {
      border: 1px solid var(--border); background: var(--bg-card);
      color: var(--text-secondary); border-radius: var(--radius-full);
      padding: 7px 14px; font-size: 12px; font-weight: 600;
      font-family: var(--font-sans); cursor: pointer;
      transition: all 160ms ease; white-space: nowrap;
    }
    .chip:hover {
      border-color: var(--border-accent); color: var(--accent);
      background: var(--accent-subtle); transform: translateY(-1px);
    }

    .input-row { display: flex; gap: 10px; align-items: stretch; }

    .input-wrap { flex: 1; position: relative; }
    .input-wrap input {
      width: 100%; background: var(--bg-input);
      border: 1px solid var(--border); border-radius: var(--radius-md);
      padding: 12px 16px; font-size: 14px; font-family: var(--font-sans);
      color: var(--text-primary); transition: all 200ms ease;
    }
    .input-wrap input::placeholder { color: var(--text-muted); }
    .input-wrap input:focus {
      outline: none; border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow), var(--shadow-sm);
    }

    .file-row { display: flex; gap: 10px; align-items: stretch; }
    .file-row .input-wrap input { font-family: var(--font-mono); font-size: 13px; }

    .stats-bar {
      display: flex; align-items: center;
      justify-content: space-between; gap: 12px; flex-wrap: wrap;
    }
    .stats-left { display: flex; gap: 16px; }
    .stat {
      font-size: 11px; color: var(--text-muted); font-weight: 600;
      display: flex; align-items: center; gap: 5px;
    }
    .stat-val { color: var(--text-secondary); font-family: var(--font-mono); }
    .stats-right { font-size: 11px; color: var(--text-muted); }
    .stats-right kbd {
      background: var(--bg-elevated); border: 1px solid var(--border);
      border-radius: 4px; padding: 1px 5px; font-family: var(--font-mono);
      font-size: 10px;
    }

    /* ═══════════════════════════════════════════
       RENAME INLINE EDIT
       ═══════════════════════════════════════════ */
    .rename-input {
      background: var(--bg-input);
      border: 1px solid var(--accent);
      border-radius: 4px;
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      padding: 2px 6px;
      width: 100%;
      outline: none;
    }

    /* ═══════════════════════════════════════════
       MOBILE OVERLAY
       ═══════════════════════════════════════════ */
    .sidebar-overlay {
      display: none;
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.6);
      z-index: 9;
    }

    /* ═══════════════════════════════════════════
       RESPONSIVE
       ═══════════════════════════════════════════ */
    @media (max-width: 768px) {
      .sidebar {
        position: fixed; left: 0; top: 0; height: 100%;
        transform: translateX(-100%);
        z-index: 10;
      }
      .sidebar.open { transform: translateX(0); }
      .sidebar-overlay.open { display: block; }
      .hamburger { display: flex; }
      .header { padding: 10px 16px; }
      #chat { padding: 14px 16px; }
      .bottom { padding: 12px 16px; }
      .msg { max-width: 92%; }
      .feature-grid { grid-template-columns: 1fr; }
      .welcome { padding: 24px 12px 16px; }
      .welcome h2 { font-size: 18px; }
      .input-row, .file-row { flex-direction: column; }
    }

    @media (max-width: 480px) {
      .status-label { display: none; }
      .stats-right { display: none; }
    }
  </style>
</head>
<body>

<div class="sidebar-overlay" id="sidebarOverlay"></div>

<div class="layout">
  <!-- ═══ SIDEBAR ═══ -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <div class="lynx-icon">
          <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
        </div>
        <h1>Angry<span>Lynx</span> AI</h1>
      </div>
      <button class="btn-new-chat" id="newChatBtn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New chat
      </button>
    </div>

    <div class="chat-list" id="chatList"></div>

    <div class="sidebar-footer">
      BojanBot &mdash; Groq &middot; Llama 3.1
    </div>
  </aside>

  <!-- ═══ MAIN ═══ -->
  <div class="main">
    <header class="header">
      <div class="header-left">
        <button class="hamburger" id="hamburgerBtn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="header-title" id="headerTitle">New chat</div>
      </div>
      <div class="header-right">
        <div class="status-dot"></div>
        <span class="status-label">Online</span>
        <button class="btn btn-ghost" id="clearBtn" title="Reset this chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
          Reset
        </button>
      </div>
    </header>

    <div id="chat">
      <div class="welcome" id="welcomeCard">
        <div class="welcome-icon">
          <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/></svg>
        </div>
        <h2>Welcome to <span>BojanBot</span></h2>
        <p>Your AI-powered coding assistant. Load files, ask questions, get instant help with code reviews, refactoring, architecture, and debugging.</p>
        <div class="feature-grid">
          <div class="feature-card">
            <span class="icon">&lt;/&gt;</span>
            <strong>Code Analysis</strong>
            <small>Load any file and get instant bug reports and reviews.</small>
          </div>
          <div class="feature-card">
            <span class="icon">&#9881;</span>
            <strong>Architecture</strong>
            <small>System design advice and implementation plans.</small>
          </div>
          <div class="feature-card">
            <span class="icon">&#9889;</span>
            <strong>Fast Answers</strong>
            <small>Blazing-fast responses powered by Groq.</small>
          </div>
        </div>
      </div>
    </div>

    <div class="bottom">
      <div class="chips">
        <button class="chip" data-quick="Analyze this code for bugs, edge cases, and potential improvements.">Bug Review</button>
        <button class="chip" data-quick="Explain this code section by section.">Explain Code</button>
        <button class="chip" data-quick="Rewrite this function to be cleaner and more efficient.">Refactor</button>
        <button class="chip" data-quick="Give me a concise, step-by-step implementation plan.">Plan</button>
        <button class="chip" data-quick="Write unit tests for this code.">Write Tests</button>
      </div>

      <div class="input-row">
        <div class="input-wrap">
          <input id="message" type="text" placeholder="Ask BojanBot anything..." autocomplete="off" />
        </div>
        <button class="btn btn-accent" id="sendBtn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          Send
        </button>
      </div>

      <div class="file-row">
        <div class="input-wrap">
          <input id="filePath" type="text" placeholder="Load file &#8594; /path/to/file.py" autocomplete="off" />
        </div>
        <button class="btn" id="loadBtn">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          Load
        </button>
      </div>

      <div class="stats-bar">
        <div class="stats-left">
          <div class="stat">Turns <span class="stat-val" id="turnStat">0</span></div>
          <div class="stat">Files <span class="stat-val" id="loadedStat">0</span></div>
          <div class="stat">Model <span class="stat-val">llama-3.1-8b</span></div>
        </div>
        <div class="stats-right">
          <kbd>Enter</kbd> to send &middot; <kbd>Shift+Enter</kbd> for file
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════
     JAVASCRIPT
     ═══════════════════════════════════════════ -->
<script>
const chatEl      = document.getElementById("chat");
const msgInput    = document.getElementById("message");
const sendBtn     = document.getElementById("sendBtn");
const clearBtn    = document.getElementById("clearBtn");
const loadBtn     = document.getElementById("loadBtn");
const fileInput   = document.getElementById("filePath");
const turnStat    = document.getElementById("turnStat");
const loadedStat  = document.getElementById("loadedStat");
const chatList    = document.getElementById("chatList");
const newChatBtn  = document.getElementById("newChatBtn");
const headerTitle = document.getElementById("headerTitle");
const sidebar     = document.getElementById("sidebar");
const overlay     = document.getElementById("sidebarOverlay");
const hamburger   = document.getElementById("hamburgerBtn");
const chips       = document.querySelectorAll("[data-quick]");

let turns = 0;
let files = 0;
let activeChatId = null;

/* ── helpers ──────────────────────────────────── */

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
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');

  const parts = html.split(/(<pre>[\s\S]*?<\/pre>)/g);
  html = parts.map(function(part) {
    if (part.startsWith('<pre>')) return part;
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

/* ── sidebar ──────────────────────────────────── */

function toggleSidebar() {
  sidebar.classList.toggle("open");
  overlay.classList.toggle("open");
}

hamburger.addEventListener("click", toggleSidebar);
overlay.addEventListener("click", toggleSidebar);

async function loadChatList() {
  const data = await getJSON("/api/chats");
  chatList.innerHTML = "";
  data.forEach(function(c) {
    if (c.active) {
      activeChatId = c.id;
      headerTitle.textContent = c.title;
      turns = c.turn;
      syncStats();
    }

    const item = document.createElement("div");
    item.className = "chat-item" + (c.active ? " active" : "");
    item.innerHTML =
      '<div class="chat-item-info">' +
        '<div class="chat-item-title">' + escHtml(c.title) + '</div>' +
        '<div class="chat-item-meta">' + timeAgo(c.created) + ' &middot; ' + c.turn + ' turns</div>' +
      '</div>' +
      '<div class="chat-item-actions">' +
        '<button class="chat-item-btn rename" title="Rename">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>' +
        '</button>' +
        '<button class="chat-item-btn delete" title="Delete">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>' +
        '</button>' +
      '</div>';

    // click to switch
    item.querySelector(".chat-item-info").addEventListener("click", function() {
      switchChat(c.id);
    });

    // rename
    item.querySelector(".rename").addEventListener("click", function(e) {
      e.stopPropagation();
      startRename(c.id, item.querySelector(".chat-item-title"));
    });

    // delete
    item.querySelector(".delete").addEventListener("click", function(e) {
      e.stopPropagation();
      deleteChat(c.id);
    });

    chatList.appendChild(item);
  });
}

function escHtml(s) {
  var d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function startRename(chatId, titleEl) {
  const current = titleEl.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "rename-input";
  input.value = current;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  function finish() {
    const newTitle = input.value.trim() || current;
    postJSON("/api/chats/rename", { id: chatId, title: newTitle }).then(function() {
      loadChatList();
    });
  }

  input.addEventListener("blur", finish);
  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") { input.value = current; input.blur(); }
  });
}

async function switchChat(chatId) {
  if (chatId === activeChatId) return;
  await postJSON("/api/chats/switch", { id: chatId });
  // reload chat messages from history
  const data = await getJSON("/api/chats/history?id=" + chatId);
  activeChatId = chatId;
  turns = data.turn || 0;
  files = (data.loaded_files || []).length;
  syncStats();
  rebuildChat(data.messages || []);
  headerTitle.textContent = data.title || "Chat";
  loadChatList();
  if (sidebar.classList.contains("open")) toggleSidebar();
}

async function deleteChat(chatId) {
  await postJSON("/api/chats/delete", { id: chatId });
  // reload everything
  const data = await getJSON("/api/chats");
  if (data.length > 0) {
    const active = data.find(function(c) { return c.active; }) || data[0];
    await switchChat(active.id);
  }
  loadChatList();
}

async function createNewChat() {
  const data = await postJSON("/api/chats/new", {});
  activeChatId = data.id;
  turns = 0;
  files = 0;
  syncStats();
  headerTitle.textContent = "New chat";
  rebuildChat([]);
  loadChatList();
  msgInput.focus();
  if (sidebar.classList.contains("open")) toggleSidebar();
}

newChatBtn.addEventListener("click", createNewChat);

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
    '<p>Your AI-powered coding assistant. Start a conversation or load a file.</p>' +
    '<div class="feature-grid">' +
      '<div class="feature-card"><span class="icon">&lt;/&gt;</span><strong>Code Analysis</strong><small>Load any file and get instant bug reports and reviews.</small></div>' +
      '<div class="feature-card"><span class="icon">&#9881;</span><strong>Architecture</strong><small>System design advice and implementation plans.</small></div>' +
      '<div class="feature-card"><span class="icon">&#9889;</span><strong>Fast Answers</strong><small>Blazing-fast responses powered by Groq.</small></div>' +
    '</div>';
  chatEl.appendChild(card);
}

/* ── messages ──────────────────────────────────── */

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

function showTyping() {
  hideWelcome();
  const el = document.createElement("div");
  el.className = "typing"; el.id = "typingIndicator";
  el.innerHTML = "<span></span><span></span><span></span>";
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

/* ── send / load / reset ─────────────────────── */

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;

  turns++;
  syncStats();
  addMsg(text, "user", false, false);
  msgInput.value = "";
  sendBtn.disabled = true;
  showTyping();

  try {
    const data = await postJSON("/chat", { message: text });
    hideTyping();
    if (data.error) {
      addMsg(data.error, "error", false, false);
    } else {
      addMsg(data.reply, "bot", true, false);
    }
    // refresh sidebar to pick up auto-title
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

/* ── event listeners ──────────────────────────── */

sendBtn.addEventListener("click", sendMessage);
clearBtn.addEventListener("click", clearChat);
loadBtn.addEventListener("click", loadFile);

chips.forEach(function(btn) {
  btn.addEventListener("click", function() {
    msgInput.value = btn.dataset.quick || "";
    msgInput.focus();
  });
});

msgInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  if (e.key === "Enter" && e.shiftKey)  { e.preventDefault(); fileInput.focus(); }
});

fileInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter") { e.preventDefault(); loadFile(); }
});

/* ── init ─────────────────────────────────────── */

(async function init() {
  await loadChatList();
  // load active chat history
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
  msgInput.focus();
})();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════
#  HTTP SERVER
# ═══════════════════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            self._send_html(HTML)
            return

        if self.path == "/api/chats":
            self._send_json(200, manager.list_chats())
            return

        if self.path.startswith("/api/chats/history"):
            # parse ?id=xxx
            chat_id = ""
            if "?" in self.path:
                params = self.path.split("?", 1)[1]
                for part in params.split("&"):
                    if part.startswith("id="):
                        chat_id = part[3:]
            if chat_id and chat_id in manager.chats:
                c = manager.chats[chat_id]
                self._send_json(200, {
                    "title": c["title"],
                    "turn": c["turn"],
                    "loaded_files": c.get("loaded_files", []),
                    "messages": c["history"],
                })
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        try:
            payload = self._read_body()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if self.path == "/chat":
            msg = str(payload.get("message", "")).strip()
            if not msg:
                self._send_json(400, {"error": "Message is empty."})
                return
            try:
                reply = bot.chat(msg)
                manager.auto_title(manager.active_id, msg)
                manager.save_after_message()
                self._send_json(200, {"reply": reply})
            except Exception as exc:
                self._send_json(500, {"error": f"Model request failed: {exc}"})
            return

        if self.path == "/reset":
            bot.reset()
            manager.save_after_message()
            self._send_json(200, {"ok": True})
            return

        if self.path == "/load":
            path = str(payload.get("path", "")).strip()
            if not path:
                self._send_json(400, {"error": "Path is empty."})
                return
            filename = bot.load_file(path)
            if filename is None:
                self._send_json(404, {"error": f"File not found: {path}"})
            else:
                manager.save_after_message()
                self._send_json(200, {"filename": filename})
            return

        if self.path == "/api/chats/new":
            chat_id = manager.new_chat()
            self._send_json(200, {"id": chat_id})
            return

        if self.path == "/api/chats/switch":
            chat_id = str(payload.get("id", ""))
            if manager.switch(chat_id):
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        if self.path == "/api/chats/delete":
            chat_id = str(payload.get("id", ""))
            if manager.delete(chat_id):
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        if self.path == "/api/chats/rename":
            chat_id = str(payload.get("id", ""))
            title = str(payload.get("title", ""))
            if manager.rename(chat_id, title):
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        self._send_json(404, {"error": "Not found"})

    def log_message(self, _format, *_args):
        return


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"BojanBot UI running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
