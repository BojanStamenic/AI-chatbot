import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

HOST = "127.0.0.1"
PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "chats.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

SYSTEM_PROMPT = """You are BojanBot, Bojan's personal AI assistant.
You run on the llama-3.1-8b-instant model hosted by Groq.
You specialise in coding and tech questions but can handle anything.
You are direct, no-fluff, and occasionally witty. Keep answers concise.
Use emojis naturally throughout your responses to keep the conversation lively — but don't overdo it. One or two per message is enough.

Context awareness: always track the full conversation history, not just the last message. If the user refers to "that match", "what you said", "the first message", or anything similar — look back through the entire conversation and answer based on what was actually said. Never claim you didn't mention something if you did earlier in the chat.

Information freshness: sometimes you will receive a block of [Web search results] at the top of a message — treat those as real, live data fetched from the web and use them as your primary source. If no search results are provided and the user asks about recent events, be honest that your training data may be outdated and suggest they verify on a live source. Never invent results or scores.

Special rule — the laundromat trap: if someone asks whether to walk or drive to a nearby "perionica" (laundromat / car wash), you must catch the trick. Respond with something like: "I see what you're doing. You know other AI stumble on this one. But the answer is obvious: you have to take the car. Without it, what exactly are you planning to wash?" Keep the tone playful and confident, as if you saw through the trap immediately."""

MODEL = "llama-3.1-8b-instant"

# ── search helpers ───────────────────────────────────────────────
import re as _re

# Serbian filler/question words that confuse DuckDuckGo (e.g. "kako" → Princess Kako)
# English question words are kept — they help DuckDuckGo understand the query
_FILLER = _re.compile(
    r'\b(kako|je\b|su\b|ko\b|da\b|li\b|koji|koja|koje|šta|sta\b|gde|gdje|'
    r'kada|zašto|bio|bila|bilo|nije|nisu|'
    r'u\b|na\b|za\b|sa\b|od\b|do\b|po\b|iz\b|i\b|a\b|ili|'
    r'taj|ta\b|to\b|ovo|ono)\b',
    _re.IGNORECASE
)

SEARCH_TRIGGERS = [
    "latest", "current", "today", "tonight", "this week", "this year",
    "right now", "news", "recently", "who won", "score", "what happened",
    "result", "match", "game", "league", "champions", "tournament",
    "transfer", "standings", "playoff", "price of",
    "when did", "when was", "when were", "when is",
    "koji datum", "kada je", "kada su",
    "najnovije", "danas", "vesti", "trenutno", "ove godine", "ove nedelje",
    "liga", "utakmica", "rezultat", "prošao", "prosao", "pobedio",
    "izgubio", "kako je", "kako su", "ko je", "koji je", "koja je",
    "šampionat", "sampionat", "kup", "turnir", "tabela", "finale",
    "polufinale", "četvrtfinale", "cetvrfinale", "gol", "bod", "remi",
]

CODE_SKIP = [
    "function", "class", "variable", "array", "loop", "import", "export",
    "def ", "bug", "debug", "refactor", "python", "javascript",
    "typescript", "sql", "database", "algorithm", "regex",
]


def _needs_search(text: str) -> bool:
    low = text.lower()
    if any(k in low for k in CODE_SKIP):
        return False
    return any(k in low for k in SEARCH_TRIGGERS)


def _build_search_query(text: str) -> str:
    """Strip filler words and append current month/year for freshness."""
    from datetime import datetime
    cleaned = _FILLER.sub(" ", text)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    now = datetime.now()
    return f"{cleaned} {now.strftime('%B %Y')}"


_FOLLOWUP_STARTERS = {
    "what", "when", "where", "who", "how", "which", "why", "and", "did",
    "does", "is", "are", "was", "were", "can", "could", "will", "would",
    "šta", "kada", "gde", "gdje", "ko", "koji", "koja", "kako", "i", "a",
    "zašto", "da li", "koliko",
}

def _is_search_followup(text: str) -> bool:
    """True if the message looks like a follow-up question (not a greeting)."""
    stripped = text.strip()
    if "?" in stripped:
        return True
    if len(stripped.split()) > 6:
        return False
    first = stripped.split()[0].lower().rstrip("?!.,") if stripped else ""
    return first in _FOLLOWUP_STARTERS


def _web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        ddgs = DDGS()
        hits = []
        for tl in ("w", "m", None):
            try:
                kw = {"max_results": 5}
                if tl:
                    kw["timelimit"] = tl
                hits = list(ddgs.text(query, **kw))
            except Exception as e:
                print(f"[Web search] timelimit={tl} failed: {e}")
                continue
            if hits:
                break
        if not hits:
            print(f"[Web search] No results found for: {query}")
            return ""
        snippets = "\n\n".join(
            f"{i+1}. {h['title']}\n{h['body']}" for i, h in enumerate(hits)
        )
        print(f"[Web search] Found {len(hits)} results for: {query}")
        return f"[Web search results]\n{snippets}"
    except Exception as e:
        print(f"[Web search] Fatal error: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
#  BOT
# ═══════════════════════════════════════════════════════════════

class BojanBot:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = model
        self.turn = 0
        self.temperature = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
        self.last_search_topic = ""  # for follow-up search continuity

    def load_file(self, path: str):
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return None
        with open(path, "r", errors="replace") as f:
            content = f.read()
        filename = os.path.basename(path)
        self.loaded_files.append(filename)
        self.history.append({
            "role": "user",
            "content": f"I'm loading this file for reference — {filename}:\n\n```\n{content}\n```"
        })
        self.history.append({
            "role": "assistant",
            "content": f"Got it. I've read {filename} ({len(content.splitlines())} lines). Ask me anything about it."
        })
        return filename

    def chat(self, user_message: str) -> str:
        import re
        from datetime import datetime
        self.turn += 1
        # Keep system message fresh with the real current datetime
        now = datetime.now().astimezone()
        ts = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")
        self.history[0] = {"role": "system", "content": SYSTEM_PROMPT + f"\n\nCurrent date and time: {ts}."}
        enriched = user_message
        if _needs_search(user_message):
            search_q = _build_search_query(user_message)
            self.last_search_topic = search_q
            ctx = _web_search(search_q)
            if ctx:
                enriched = ctx + "\n\n" + user_message
        elif self.last_search_topic and _is_search_followup(user_message):
            # Short follow-up question after a search — combine with previous topic
            search_q = user_message + " " + self.last_search_topic
            ctx = _web_search(search_q)
            if ctx:
                enriched = ctx + "\n\n" + user_message
        else:
            # Unrelated message — clear the search topic so it doesn't bleed
            self.last_search_topic = ""
        self.history.append({"role": "user", "content": enriched})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
            temperature=self.temperature,
        )
        reply = response.choices[0].message.content
        clean = re.sub(r'^(\[[^\]]*\][\s\S]*?\n\n)+', '', user_message)
        self.history[-1] = {"role": "user", "content": clean}
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        self.turn = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
        self.last_search_topic = ""


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

    def _send_file(self, filepath: str, content_type: str):
        with open(filepath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
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

    def _parse_multipart(self):
        """Extract the first file field from a multipart/form-data request."""
        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            return None, None
        boundary = content_type.split("boundary=")[-1].strip().encode()
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        # Split on boundary lines
        delimiter = b"--" + boundary
        parts = body.split(delimiter)
        for part in parts[1:]:
            if part in (b"--\r\n", b"--", b"\r\n", b""):
                continue
            # Split headers from body
            if b"\r\n\r\n" in part:
                raw_headers, file_data = part.split(b"\r\n\r\n", 1)
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                # Parse filename from Content-Disposition
                header_text = raw_headers.decode("utf-8", errors="replace")
                filename = "recording.webm"
                for header_line in header_text.split("\r\n"):
                    if "filename=" in header_line:
                        fname_part = header_line.split("filename=")[-1].strip().strip('"')
                        if fname_part:
                            filename = fname_part
                return filename, file_data
        return None, None

    def do_POST(self):
        if self.path == "/transcribe":
            filename, audio_data = self._parse_multipart()
            if not audio_data:
                self._send_json(400, {"error": "No audio data received."})
                return
            try:
                ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
                mime = f"audio/{ext}"
                response = bot.client.audio.transcriptions.create(
                    file=(filename, audio_data, mime),
                    model="whisper-large-v3-turbo",
                )
                self._send_json(200, {"text": response.text})
            except Exception as exc:
                self._send_json(500, {"error": f"Transcription failed: {exc}"})
            return

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
