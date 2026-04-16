import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from chatbot import BojanBot

HOST = "127.0.0.1"
PORT = 8080

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("Missing GROQ_API_KEY. Add it to .env or export it before starting the UI.")

bot = BojanBot(api_key=api_key)

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
       DESIGN TOKENS
       ═══════════════════════════════════════════ */
    :root {
      --bg-deep:       #06080d;
      --bg-surface:    #0c1017;
      --bg-card:       #111722;
      --bg-elevated:   #161d2b;
      --bg-input:      #0f1520;

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
      --font-mono:     'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;

      --radius-sm:     8px;
      --radius-md:     12px;
      --radius-lg:     16px;
      --radius-xl:     20px;
      --radius-full:   9999px;

      --shadow-sm:     0 2px 8px rgba(0,0,0,0.3);
      --shadow-md:     0 8px 30px rgba(0,0,0,0.4);
      --shadow-lg:     0 20px 60px rgba(0,0,0,0.5);
      --shadow-glow:   0 0 40px var(--accent-glow);
    }

    /* ═══════════════════════════════════════════
       RESET & BASE
       ═══════════════════════════════════════════ */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html { font-size: 16px; -webkit-font-smoothing: antialiased; }

    body {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: var(--font-sans);
      color: var(--text-primary);
      background: var(--bg-deep);
      overflow: hidden;
    }

    /* ═══════════════════════════════════════════
       ANIMATED BACKGROUND
       ═══════════════════════════════════════════ */
    body::before {
      content: '';
      position: fixed;
      inset: 0;
      background:
        radial-gradient(ellipse 800px 600px at 20% 10%, rgba(239,127,26,0.07) 0%, transparent 60%),
        radial-gradient(ellipse 600px 500px at 80% 90%, rgba(59,130,246,0.05) 0%, transparent 60%),
        radial-gradient(ellipse 400px 400px at 50% 50%, rgba(139,92,246,0.03) 0%, transparent 60%);
      animation: bgPulse 8s ease-in-out infinite alternate;
      pointer-events: none;
      z-index: 0;
    }

    @keyframes bgPulse {
      0%   { opacity: 0.6; transform: scale(1); }
      100% { opacity: 1;   transform: scale(1.05); }
    }

    /* grid overlay */
    body::after {
      content: '';
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 60px 60px;
      pointer-events: none;
      z-index: 0;
    }

    /* ═══════════════════════════════════════════
       APP SHELL
       ═══════════════════════════════════════════ */
    .app {
      position: relative;
      z-index: 1;
      width: min(1200px, calc(100vw - 32px));
      height: min(94vh, 920px);
      border-radius: var(--radius-xl);
      overflow: hidden;
      border: 1px solid var(--border);
      background: var(--bg-surface);
      box-shadow: var(--shadow-lg), 0 0 80px rgba(239,127,26,0.04);
      display: grid;
      grid-template-rows: auto 1fr auto;
      animation: appRise 500ms cubic-bezier(0.16, 1, 0.3, 1);
    }

    @keyframes appRise {
      from { opacity: 0; transform: translateY(20px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* ═══════════════════════════════════════════
       HEADER
       ═══════════════════════════════════════════ */
    .header {
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(17,23,34,0.95), var(--bg-surface));
      backdrop-filter: blur(20px);
      flex-wrap: wrap;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    /* Lynx icon */
    .lynx-icon {
      width: 44px;
      height: 44px;
      border-radius: var(--radius-md);
      background: linear-gradient(135deg, var(--accent), #d66908);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 16px var(--accent-glow);
      flex-shrink: 0;
      position: relative;
      overflow: hidden;
    }

    .lynx-icon::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, transparent 40%, rgba(255,255,255,0.15));
      border-radius: inherit;
    }

    .lynx-icon svg {
      width: 26px;
      height: 26px;
      fill: #fff;
      position: relative;
      z-index: 1;
    }

    .brand-text h1 {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.3px;
      line-height: 1.2;
      color: var(--text-primary);
    }

    .brand-text h1 span {
      background: linear-gradient(135deg, var(--accent), var(--accent-hover));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .brand-text p {
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 500;
      margin-top: 2px;
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px rgba(52,211,153,0.5);
      animation: pulse 2s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%      { opacity: 0.4; }
    }

    .status-label {
      font-size: 12px;
      color: var(--text-secondary);
      font-weight: 500;
    }

    /* ═══════════════════════════════════════════
       BUTTONS
       ═══════════════════════════════════════════ */
    .btn {
      border: 1px solid var(--border);
      background: var(--bg-elevated);
      color: var(--text-secondary);
      border-radius: var(--radius-sm);
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 600;
      font-family: var(--font-sans);
      cursor: pointer;
      transition: all 180ms ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }

    .btn:hover {
      background: var(--bg-card);
      color: var(--text-primary);
      border-color: rgba(255,255,255,0.12);
      transform: translateY(-1px);
      box-shadow: var(--shadow-sm);
    }

    .btn:active { transform: translateY(0); }

    .btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
      transform: none !important;
      box-shadow: none !important;
    }

    .btn-accent {
      background: linear-gradient(135deg, var(--accent), #d66908);
      border-color: transparent;
      color: #fff;
      font-weight: 700;
      box-shadow: 0 4px 14px var(--accent-glow);
    }

    .btn-accent:hover {
      background: linear-gradient(135deg, var(--accent-hover), var(--accent));
      color: #fff;
      box-shadow: 0 6px 24px var(--accent-glow);
    }

    .btn-ghost {
      background: transparent;
      border-color: transparent;
      color: var(--text-muted);
      padding: 8px 10px;
    }

    .btn-ghost:hover {
      background: var(--accent-subtle);
      color: var(--accent);
      border-color: transparent;
    }

    .btn-sm {
      padding: 6px 10px;
      font-size: 12px;
      border-radius: var(--radius-full);
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
      background:
        linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-deep) 100%);
    }

    /* custom scrollbar */
    #chat::-webkit-scrollbar { width: 6px; }
    #chat::-webkit-scrollbar-track { background: transparent; }
    #chat::-webkit-scrollbar-thumb {
      background: rgba(255,255,255,0.08);
      border-radius: 3px;
    }
    #chat::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }

    /* welcome card */
    .welcome {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      padding: 40px 20px 30px;
      gap: 20px;
      animation: fadeUp 600ms ease-out;
    }

    .welcome-icon {
      width: 72px;
      height: 72px;
      border-radius: 20px;
      background: linear-gradient(135deg, var(--accent), #d66908);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--shadow-glow);
      position: relative;
    }

    .welcome-icon::before {
      content: '';
      position: absolute;
      inset: -3px;
      border-radius: 23px;
      background: linear-gradient(135deg, var(--accent), transparent, var(--accent));
      opacity: 0.3;
      animation: spin 4s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .welcome-icon svg {
      width: 38px;
      height: 38px;
      fill: #fff;
      position: relative;
      z-index: 1;
    }

    .welcome h2 {
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -0.3px;
      color: var(--text-primary);
    }

    .welcome h2 span {
      background: linear-gradient(135deg, var(--accent), var(--accent-hover));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .welcome p {
      font-size: 14px;
      color: var(--text-secondary);
      max-width: 480px;
      line-height: 1.6;
    }

    .feature-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      width: 100%;
      max-width: 640px;
    }

    .feature-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 16px 14px;
      text-align: left;
      transition: all 200ms ease;
      cursor: default;
    }

    .feature-card:hover {
      border-color: var(--border-accent);
      background: var(--bg-elevated);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }

    .feature-card .icon {
      font-size: 20px;
      margin-bottom: 8px;
      display: block;
    }

    .feature-card strong {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-primary);
      display: block;
      margin-bottom: 4px;
    }

    .feature-card small {
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.45;
    }

    /* ═══════════════════════════════════════════
       MESSAGES
       ═══════════════════════════════════════════ */
    .msg {
      max-width: 80%;
      border-radius: var(--radius-md);
      padding: 12px 16px;
      line-height: 1.55;
      font-size: 14px;
      animation: msgIn 250ms cubic-bezier(0.16, 1, 0.3, 1);
      position: relative;
      word-wrap: break-word;
    }

    .msg pre {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 10px 12px;
      margin: 8px 0 4px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.5;
    }

    .msg code {
      font-family: var(--font-mono);
      font-size: 13px;
      background: rgba(0,0,0,0.25);
      padding: 2px 6px;
      border-radius: 4px;
    }

    .msg pre code {
      background: none;
      padding: 0;
    }

    @keyframes msgIn {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    .msg.user {
      align-self: flex-end;
      background: var(--user-bg);
      border: 1px solid var(--user-border);
      color: var(--text-primary);
    }

    .msg.bot {
      align-self: flex-start;
      background: var(--bot-bg);
      border: 1px solid var(--bot-border);
      color: var(--text-primary);
    }

    .msg.system {
      align-self: center;
      background: var(--system-bg);
      border: 1px solid var(--border);
      color: var(--text-secondary);
      font-size: 12px;
      padding: 8px 14px;
    }

    .msg.error {
      align-self: center;
      background: var(--error-bg);
      border: 1px solid var(--error-border);
      color: var(--error-text);
      font-size: 12px;
      padding: 8px 14px;
    }

    .msg-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
      display: block;
    }

    .msg.user .msg-label { color: var(--accent); }
    .msg.bot  .msg-label { color: #6391ff; }

    /* typing indicator */
    .typing {
      align-self: flex-start;
      display: flex;
      gap: 5px;
      padding: 14px 18px;
      background: var(--bot-bg);
      border: 1px solid var(--bot-border);
      border-radius: var(--radius-md);
      animation: msgIn 250ms ease-out;
    }

    .typing span {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #6391ff;
      animation: typeDot 1.2s ease-in-out infinite;
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
      padding: 16px 24px;
      background: var(--bg-surface);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* quick action chips */
    .chips {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .chip {
      border: 1px solid var(--border);
      background: var(--bg-card);
      color: var(--text-secondary);
      border-radius: var(--radius-full);
      padding: 7px 14px;
      font-size: 12px;
      font-weight: 600;
      font-family: var(--font-sans);
      cursor: pointer;
      transition: all 160ms ease;
      white-space: nowrap;
    }

    .chip:hover {
      border-color: var(--border-accent);
      color: var(--accent);
      background: var(--accent-subtle);
      transform: translateY(-1px);
    }

    /* input row */
    .input-row {
      display: flex;
      gap: 10px;
      align-items: stretch;
    }

    .input-wrap {
      flex: 1;
      position: relative;
    }

    .input-wrap input {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 12px 16px;
      font-size: 14px;
      font-family: var(--font-sans);
      color: var(--text-primary);
      transition: all 200ms ease;
    }

    .input-wrap input::placeholder { color: var(--text-muted); }

    .input-wrap input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow), var(--shadow-sm);
    }

    /* file load row */
    .file-row {
      display: flex;
      gap: 10px;
      align-items: stretch;
    }

    .file-row .input-wrap input {
      font-family: var(--font-mono);
      font-size: 13px;
    }

    /* stats bar */
    .stats-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .stats-left {
      display: flex;
      gap: 16px;
    }

    .stat {
      font-size: 11px;
      color: var(--text-muted);
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .stat-val {
      color: var(--text-secondary);
      font-family: var(--font-mono);
    }

    .stats-right {
      font-size: 11px;
      color: var(--text-muted);
    }

    .stats-right kbd {
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 1px 5px;
      font-family: var(--font-mono);
      font-size: 10px;
    }

    /* ═══════════════════════════════════════════
       RESPONSIVE
       ═══════════════════════════════════════════ */
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 768px) {
      .app {
        width: 100vw;
        height: 100vh;
        border-radius: 0;
        border: none;
      }
      .header { padding: 12px 16px; }
      .header-left { gap: 10px; }
      .lynx-icon { width: 36px; height: 36px; }
      .lynx-icon svg { width: 20px; height: 20px; }
      .brand-text h1 { font-size: 15px; }
      #chat { padding: 14px 16px; }
      .bottom { padding: 12px 16px; }
      .msg { max-width: 92%; }
      .feature-grid {
        grid-template-columns: 1fr;
        max-width: 100%;
      }
      .welcome { padding: 24px 12px 16px; }
      .welcome h2 { font-size: 18px; }
      .input-row, .file-row { flex-direction: column; }
    }

    @media (max-width: 480px) {
      .header-right .status-label { display: none; }
      .stats-right { display: none; }
    }
  </style>
</head>
<body>
  <div class="app">

    <!-- ═══ HEADER ═══ -->
    <header class="header">
      <div class="header-left">
        <div class="lynx-icon">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15.5v-2.65c-1.24-.15-2.35-.7-3.19-1.53l1.4-1.4c.63.63 1.5 1.02 2.45 1.02.34 0 .67-.05.97-.14l.03.03V17.5h-1.66zm4.93-3.57c-.14.47-.35.9-.63 1.29l-1.4-1.4c.2-.34.33-.73.37-1.14h1.98c-.04.44-.14.86-.32 1.25zm.32-2.93h-1.98a3.47 3.47 0 00-.37-1.14l1.4-1.4c.28.39.49.82.63 1.29.18.39.28.81.32 1.25zM9.47 7.72l1.4 1.4c-.2.34-.33.73-.37 1.14H8.52c.04-.44.14-.86.32-1.25.14-.47.35-.9.63-1.29zM8.52 12.26h1.98c.04.41.17.8.37 1.14l-1.4 1.4c-.28-.39-.49-.82-.63-1.29-.18-.39-.28-.81-.32-1.25zm6.28-4.54l-1.4 1.4a3.47 3.47 0 00-1.14-.37V6.77c.44.04.86.14 1.25.32.47.14.9.35 1.29.63z"/>
          </svg>
        </div>
        <div class="brand-text">
          <h1>Angry<span>Lynx</span> AI</h1>
          <p>BojanBot &mdash; powered by Groq</p>
        </div>
      </div>
      <div class="header-right">
        <div class="status-dot"></div>
        <span class="status-label">Online</span>
        <button class="btn btn-ghost" id="clearBtn" title="Clear chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
          Reset
        </button>
      </div>
    </header>

    <!-- ═══ CHAT ═══ -->
    <div id="chat">
      <div class="welcome" id="welcomeCard">
        <div class="welcome-icon">
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
        </div>
        <h2>Welcome to <span>BojanBot</span></h2>
        <p>Your AI-powered coding assistant. Load files, ask questions, get instant help with code reviews, refactoring, architecture, and debugging.</p>
        <div class="feature-grid">
          <div class="feature-card">
            <span class="icon">&lt;/&gt;</span>
            <strong>Code Analysis</strong>
            <small>Load any file and get instant bug reports, refactoring tips, and reviews.</small>
          </div>
          <div class="feature-card">
            <span class="icon">&#9881;</span>
            <strong>Architecture</strong>
            <small>Get system design advice, implementation plans, and best practices.</small>
          </div>
          <div class="feature-card">
            <span class="icon">&#9889;</span>
            <strong>Fast Answers</strong>
            <small>Powered by Groq for blazing-fast responses with Llama 3.1.</small>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ BOTTOM PANEL ═══ -->
    <div class="bottom">
      <div class="chips">
        <button class="chip" data-quick="Analyze this code for bugs, edge cases, and potential improvements.">Bug Review</button>
        <button class="chip" data-quick="Explain this code section by section.">Explain Code</button>
        <button class="chip" data-quick="Rewrite this function to be cleaner, more readable, and more efficient.">Refactor</button>
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
          <input id="filePath" type="text" placeholder="Load file &rarr; /path/to/file.py" autocomplete="off" />
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

  <!-- ═══════════════════════════════════════════
       JAVASCRIPT
       ═══════════════════════════════════════════ -->
  <script>
    const chat        = document.getElementById("chat");
    const msgInput    = document.getElementById("message");
    const sendBtn     = document.getElementById("sendBtn");
    const clearBtn    = document.getElementById("clearBtn");
    const loadBtn     = document.getElementById("loadBtn");
    const fileInput   = document.getElementById("filePath");
    const turnStat    = document.getElementById("turnStat");
    const loadedStat  = document.getElementById("loadedStat");
    const welcomeCard = document.getElementById("welcomeCard");
    const chips       = document.querySelectorAll("[data-quick]");

    let turns = 0;
    let files = 0;
    let welcomeVisible = true;

    function syncStats() {
      turnStat.textContent  = turns;
      loadedStat.textContent = files;
    }

    function hideWelcome() {
      if (!welcomeVisible) return;
      welcomeVisible = false;
      welcomeCard.style.transition = "opacity 200ms ease, transform 200ms ease";
      welcomeCard.style.opacity = "0";
      welcomeCard.style.transform = "translateY(-8px)";
      setTimeout(() => welcomeCard.remove(), 220);
    }

    function renderMarkdown(text) {
      // Basic markdown: code blocks, inline code, bold, italic
      let html = text
        // code blocks
        .replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
          return '<pre><code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code></pre>';
        })
        // inline code
        .replace(/`([^`]+)`/g, function(_, code) {
          return '<code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code>';
        })
        // bold
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // italic
        .replace(/\*(.+?)\*/g, '<em>$1</em>');

      // line breaks (but not inside pre)
      const parts = html.split(/(<pre>[\s\S]*?<\/pre>)/g);
      html = parts.map(function(part) {
        if (part.startsWith('<pre>')) return part;
        return part.replace(/\n/g, '<br>');
      }).join('');

      return html;
    }

    function addMsg(text, type, useMarkdown) {
      hideWelcome();
      const div = document.createElement("div");
      div.className = "msg " + type;

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

      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      return div;
    }

    function showTyping() {
      hideWelcome();
      const el = document.createElement("div");
      el.className = "typing";
      el.id = "typingIndicator";
      el.innerHTML = "<span></span><span></span><span></span>";
      chat.appendChild(el);
      chat.scrollTop = chat.scrollHeight;
    }

    function hideTyping() {
      const el = document.getElementById("typingIndicator");
      if (el) el.remove();
    }

    async function postJSON(url, body) {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      return res.json();
    }

    async function sendMessage() {
      const text = msgInput.value.trim();
      if (!text) return;

      turns++;
      syncStats();
      addMsg(text, "user", false);
      msgInput.value = "";
      sendBtn.disabled = true;
      showTyping();

      try {
        const data = await postJSON("/chat", { message: text });
        hideTyping();
        if (data.error) {
          addMsg(data.error, "error", false);
        } else {
          addMsg(data.reply, "bot", true);
        }
      } catch (_) {
        hideTyping();
        addMsg("Network error — could not reach the server.", "error", false);
      } finally {
        sendBtn.disabled = false;
        msgInput.focus();
      }
    }

    async function clearChat() {
      try {
        await postJSON("/reset", {});
        // rebuild chat with welcome
        chat.innerHTML = "";
        turns = 0;
        files = 0;
        syncStats();
        welcomeVisible = false; // will add fresh card
        const card = document.createElement("div");
        card.className = "welcome";
        card.id = "welcomeCard";
        card.innerHTML = `
          <div class="welcome-icon">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/></svg>
          </div>
          <h2>Welcome to <span>BojanBot</span></h2>
          <p>Session cleared. Start a fresh conversation.</p>`;
        chat.appendChild(card);
        welcomeVisible = true;
      } catch (_) {
        addMsg("Failed to clear session.", "error", false);
      }
    }

    async function loadFile() {
      const path = fileInput.value.trim();
      if (!path) return;

      loadBtn.disabled = true;
      try {
        const data = await postJSON("/load", { path: path });
        if (data.error) {
          addMsg(data.error, "error", false);
        } else {
          files++;
          syncStats();
          addMsg("Loaded " + data.filename + " into context.", "system", false);
          fileInput.value = "";
        }
      } catch (_) {
        addMsg("Failed to load file.", "error", false);
      } finally {
        loadBtn.disabled = false;
        fileInput.focus();
      }
    }

    // event listeners
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
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    fileInput.addEventListener("keydown", function(e) {
      if (e.key === "Enter") {
        e.preventDefault();
        loadFile();
      }
    });

    // also support Shift+Enter from main input to focus file input
    msgInput.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        fileInput.focus();
      }
    });

    syncStats();
    msgInput.focus();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
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

    def do_GET(self):
        if self.path == "/":
            self._send_html(HTML)
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw.decode("utf-8"))
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
                self._send_json(200, {"reply": reply})
            except Exception as exc:
                self._send_json(500, {"error": f"Model request failed: {exc}"})
            return

        if self.path == "/reset":
            bot.reset()
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
                self._send_json(200, {"filename": filename})
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
