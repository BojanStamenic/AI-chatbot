# ═══════════════════════════════════════════════════════════════
#  BojanBot — AI chatbot backend
#  Groq LLM  ·  Web search  ·  Image generation  ·  Voice
# ═══════════════════════════════════════════════════════════════

import json
import os
import re as _re
import time
import urllib.parse as _urlparse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

HOST = "127.0.0.1"
PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "chats.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
MODEL = "llama-3.1-8b-instant"


# ═══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are BojanBot, Bojan's personal AI assistant.
You run on the llama-3.1-8b-instant model hosted by Groq.
You specialise in coding and tech questions but can handle anything.
You are direct, no-fluff, and occasionally witty. Keep answers concise.
Use emojis naturally throughout your responses to keep the conversation lively — but don't overdo it. One or two per message is enough.

Context awareness: always track the full conversation history, not just the last message. If the user refers to "that match", "what you said", "the first message", or anything similar — look back through the entire conversation and answer based on what was actually said. Never claim you didn't mention something if you did earlier in the chat.

Information freshness: sometimes you will receive a block of [Web search results] at the top of a message — treat those as real, live data fetched from the web and use them as your primary source. If no search results are provided and the user asks about recent events, be honest that your training data may be outdated and suggest they verify on a live source. Never invent results or scores.

Special rule — the laundromat trap: if someone asks whether to walk or drive to a nearby "perionica" (laundromat / car wash), you must catch the trick. Respond with something like: "I see what you're doing. You know other AI stumble on this one. But the answer is obvious: you have to take the car. Without it, what exactly are you planning to wash?" Keep the tone playful and confident, as if you saw through the trap immediately."""


# ═══════════════════════════════════════════════════════════════
#  WEB SEARCH — DuckDuckGo pretraga za sveze informacije
#  Detektuje upite o aktuelnostima, stripuje srpske filler reci,
#  i obogacuje poruku rezultatima pretrage.
# ═══════════════════════════════════════════════════════════════

# Srpske filler reci koje bune DuckDuckGo (npr. "kako" → Princess Kako)
_FILLER = _re.compile(
    r'\b(kako|je\b|su\b|ko\b|da\b|li\b|koji|koja|koje|šta|sta\b|gde|gdje|'
    r'kada|zašto|bio|bila|bilo|nije|nisu|'
    r'u\b|na\b|za\b|sa\b|od\b|do\b|po\b|iz\b|i\b|a\b|ili|'
    r'taj|ta\b|to\b|ovo|ono)\b',
    _re.IGNORECASE
)

# Kljucne reci koje trigeruju web pretragu (EN + SR)
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

# Ako poruka sadrzi ove reci → NE trigeruj pretragu (kodiranje pitanje)
CODE_SKIP = [
    "function", "class", "variable", "array", "loop", "import", "export",
    "def ", "bug", "debug", "refactor", "python", "javascript",
    "typescript", "sql", "database", "algorithm", "regex",
]

# Reci kojima pocinje follow-up pitanje posle pretrage
_FOLLOWUP_STARTERS = {
    "what", "when", "where", "who", "how", "which", "why", "and", "did",
    "does", "is", "are", "was", "were", "can", "could", "will", "would",
    "šta", "kada", "gde", "gdje", "ko", "koji", "koja", "kako", "i", "a",
    "zašto", "da li", "koliko",
}


def _needs_search(text: str) -> bool:
    """Da li poruka zahteva web pretragu?"""
    low = text.lower()
    if any(k in low for k in CODE_SKIP):
        return False
    return any(k in low for k in SEARCH_TRIGGERS)


def _build_search_query(text: str) -> str:
    """Ocisti filler reci i dodaj mesec/godinu za svezinu rezultata."""
    from datetime import datetime
    cleaned = _FILLER.sub(" ", text)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    now = datetime.now()
    return f"{cleaned} {now.strftime('%B %Y')}"


def _is_search_followup(text: str) -> bool:
    """Da li poruka izgleda kao follow-up pitanje (ne pozdrav)?"""
    stripped = text.strip()
    if "?" in stripped:
        return True
    if len(stripped.split()) > 6:
        return False
    first = stripped.split()[0].lower().rstrip("?!.,") if stripped else ""
    return first in _FOLLOWUP_STARTERS


def _web_search(query: str) -> str:
    """Pozovi DuckDuckGo i vrati snippet rezultata."""
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
#  IMAGE GENERATION — Pollinations AI proxy
#  Detektuje zahteve za sliku, izvlaci prompt, vraca lokalni
#  proxy URL koji backend fetcha da izbegne referrer blokade.
# ═══════════════════════════════════════════════════════════════

# Trigger fraze za generisanje slika (EN + SR)
IMAGE_TRIGGERS = [
    "generate image", "create image", "make image", "draw me", "draw a",
    "generate a picture", "create a picture", "make a picture",
    "image of", "picture of", "photo of",
    "napravi sliku", "generiši sliku", "generisi sliku", "nacrtaj",
    "kreiraj sliku", "napravi mi sliku", "generisi mi sliku",
    "generate an image", "create an image", "make an image",
    "napravi mi", "generisi mi", "generiši mi",
]


def _needs_image(text: str) -> bool:
    """Da li poruka trazi generisanje slike?"""
    low = text.lower()
    return any(k in low for k in IMAGE_TRIGGERS)


def _extract_image_prompt(text: str) -> str:
    """Izvuci opis slike iz korisnicke poruke."""
    low = text.lower()
    for trigger in sorted(IMAGE_TRIGGERS, key=len, reverse=True):
        if trigger in low:
            idx = low.index(trigger) + len(trigger)
            rest = text[idx:].strip().lstrip(":.,").strip()
            if rest:
                return rest
    return text


def _generate_image_url(prompt: str) -> str:
    """Vrati lokalni proxy URL — backend fetcha sliku da izbegne referrer blokade."""
    encoded = _urlparse.quote(prompt)
    return f"/api/image?prompt={encoded}"


# ═══════════════════════════════════════════════════════════════
#  BOT — Groq LLM wrapper sa istorijom poruka
#  Salje poruke na Groq API, obogacuje ih web pretragom,
#  cuva istoriju konverzacije i ucitane fajlove.
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
        self.last_search_topic = ""

    # ── ucitavanje fajla u kontekst ─────────────────────────

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

    # ── slanje poruke i dobijanje odgovora ──────────────────

    def chat(self, user_message: str) -> str:
        import re
        from datetime import datetime
        self.turn += 1

        # Osvezi system poruku sa trenutnim datumom/vremenom
        now = datetime.now().astimezone()
        ts = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")
        self.history[0] = {"role": "system", "content": SYSTEM_PROMPT + f"\n\nCurrent date and time: {ts}."}

        # Obogati poruku web pretragom ako treba
        enriched = user_message
        if _needs_search(user_message):
            search_q = _build_search_query(user_message)
            self.last_search_topic = search_q
            ctx = _web_search(search_q)
            if ctx:
                enriched = ctx + "\n\n" + user_message
        elif self.last_search_topic and _is_search_followup(user_message):
            search_q = user_message + " " + self.last_search_topic
            ctx = _web_search(search_q)
            if ctx:
                enriched = ctx + "\n\n" + user_message
        else:
            self.last_search_topic = ""

        # Posalji na Groq API
        self.history.append({"role": "user", "content": enriched})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.history,
            temperature=self.temperature,
        )
        reply = response.choices[0].message.content

        # Sacuvaj cistu poruku u istoriju (bez search rezultata)
        clean = re.sub(r'^(\[[^\]]*\][\s\S]*?\n\n)+', '', user_message)
        self.history[-1] = {"role": "user", "content": clean}
        self.history.append({"role": "assistant", "content": reply})
        return reply

    # ── resetovanje sesije ──────────────────────────────────

    def reset(self):
        self.turn = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
        self.last_search_topic = ""


# ═══════════════════════════════════════════════════════════════
#  BOT INSTANCA
# ═══════════════════════════════════════════════════════════════

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("Missing GROQ_API_KEY. Add it to .env or export it before starting the UI.")

bot = BojanBot(api_key=api_key)


# ═══════════════════════════════════════════════════════════════
#  CHAT MANAGER — multi-chat sa JSON perzistencijom
#  Upravlja vise chatova, cuva ih u chats.json,
#  omogucava switch, rename, delete, auto-title.
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

    # ── perzistencija (load/save iz JSON fajla) ─────────────

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

    # ── interni helperi ─────────────────────────────────────

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

    # ── javni API (new, switch, delete, rename, list) ───────

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
        """Postavi title iz prve poruke ako je jos default."""
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
#  HTTP SERVER — rute i handler
#  GET:  /  /api/chats  /api/chats/history  /api/image
#  POST: /chat  /transcribe  /reset  /load  /api/chats/*
# ═══════════════════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):

    # ── helper metode za HTTP response ──────────────────────

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

    # ── multipart parser (za audio upload) ──────────────────

    def _parse_multipart(self):
        """Izvuci prvi fajl iz multipart/form-data requesta."""
        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            return None, None
        boundary = content_type.split("boundary=")[-1].strip().encode()
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        delimiter = b"--" + boundary
        parts = body.split(delimiter)
        for part in parts[1:]:
            if part in (b"--\r\n", b"--", b"\r\n", b""):
                continue
            if b"\r\n\r\n" in part:
                raw_headers, file_data = part.split(b"\r\n\r\n", 1)
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                header_text = raw_headers.decode("utf-8", errors="replace")
                filename = "recording.webm"
                for header_line in header_text.split("\r\n"):
                    if "filename=" in header_line:
                        fname_part = header_line.split("filename=")[-1].strip().strip('"')
                        if fname_part:
                            filename = fname_part
                return filename, file_data
        return None, None

    # ── GET rute ────────────────────────────────────────────

    def do_GET(self):

        # Glavna stranica
        if self.path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return

        # Lista svih chatova
        if self.path == "/api/chats":
            self._send_json(200, manager.list_chats())
            return

        # Istorija jednog chata
        if self.path.startswith("/api/chats/history"):
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

        # Image proxy — backend fetcha sliku sa Pollinations da izbegne referrer blokadu
        if self.path.startswith("/api/image"):
            prompt = ""
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("prompt="):
                        prompt = _urlparse.unquote(part[7:])
            if not prompt:
                self._send_json(400, {"error": "Missing prompt"})
                return
            try:
                from urllib.request import urlopen, Request
                poll_url = (
                    "https://image.pollinations.ai/prompt/"
                    + _urlparse.quote(prompt)
                    + "?width=1024&height=1024&nologo=true"
                )
                req = Request(poll_url, headers={"User-Agent": "BojanBot/1.0"})
                with urlopen(req, timeout=90) as resp:
                    img_data = resp.read()
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(img_data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(img_data)
            except Exception as exc:
                self._send_json(500, {"error": f"Image generation failed: {exc}"})
            return

        # Staticki fajlovi (CSS, JS, slike) iz static/ direktorijuma
        static_path = self.path.lstrip("/")
        if ".." not in static_path:
            filepath = os.path.join(STATIC_DIR, static_path)
            if os.path.isfile(filepath):
                ext = os.path.splitext(filepath)[1].lower()
                ctypes = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".ico": "image/x-icon",
                }
                self._send_file(filepath, ctypes.get(ext, "application/octet-stream"))
                return

        self._send_json(404, {"error": "Not found"})

    # ── POST rute ───────────────────────────────────────────

    def do_POST(self):

        # Transkripcija glasa (Whisper via Groq)
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

        # Slanje poruke (sa auto-detekcijom slike i pretrage)
        if self.path == "/chat":
            msg = str(payload.get("message", "")).strip()
            if not msg:
                self._send_json(400, {"error": "Message is empty."})
                return

            # → Generisanje slike ako je detektovan image request
            if _needs_image(msg):
                prompt = _extract_image_prompt(msg)
                image_url = _generate_image_url(prompt)
                bot.turn += 1
                bot.history.append({"role": "user", "content": msg})
                reply = f"Here's your generated image! 🎨\n\n![{prompt}]({image_url})"
                bot.history.append({"role": "assistant", "content": reply})
                manager.auto_title(manager.active_id, msg)
                manager.save_after_message()
                self._send_json(200, {"reply": reply})
                return

            # → Normalan chat (sa opcionalnom web pretragom)
            try:
                reply = bot.chat(msg)
                manager.auto_title(manager.active_id, msg)
                manager.save_after_message()
                self._send_json(200, {"reply": reply})
            except Exception as exc:
                self._send_json(500, {"error": f"Model request failed: {exc}"})
            return

        # Reset sesije
        if self.path == "/reset":
            bot.reset()
            manager.save_after_message()
            self._send_json(200, {"ok": True})
            return

        # Ucitavanje fajla u kontekst
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

        # Novi chat
        if self.path == "/api/chats/new":
            chat_id = manager.new_chat()
            self._send_json(200, {"id": chat_id})
            return

        # Prebacivanje na drugi chat
        if self.path == "/api/chats/switch":
            chat_id = str(payload.get("id", ""))
            if manager.switch(chat_id):
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        # Brisanje chata
        if self.path == "/api/chats/delete":
            chat_id = str(payload.get("id", ""))
            if manager.delete(chat_id):
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

        # Preimenovanje chata
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


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

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
