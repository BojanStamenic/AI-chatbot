import json
import os
import urllib.parse as _urlparse
from http.server import BaseHTTPRequestHandler

from core.config import STATIC_DIR
from image.image_gen import needs_image, extract_image_prompt, generate_image_url
from voice.transcribe import parse_multipart, transcribe_audio


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

    # ── GET rute ────────────────────────────────────────────

    def do_GET(self):
        from chatbot_ui import manager

        if self.path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return

        if self.path == "/api/chats":
            self._send_json(200, manager.list_chats())
            return

        if self.path.startswith("/api/chats/history"):
            chat_id = ""
            if "?" in self.path:
                params = self.path.split("?", 1)[1]
                for part in params.split("&"):
                    if part.startswith("id="):
                        chat_id = part[3:]
            if chat_id and chat_id in manager.chats:
                c = manager.chats[chat_id]
                
                # Filter history to only include user and assistant messages with content
                # Hide internal tool messages and tool_calls from frontend
                filtered_messages = []
                for msg in c["history"]:
                    role = msg.get("role")
                    # Skip system, tool messages, and assistant messages without content
                    if role == "system" or role == "tool":
                        continue
                    if role == "assistant" and not msg.get("content"):
                        continue  # Skip assistant messages that only have tool_calls
                    # Include user and assistant messages with actual content
                    if role in ("user", "assistant") and msg.get("content"):
                        filtered_messages.append({
                            "role": role,
                            "content": msg["content"]
                        })
                
                self._send_json(200, {
                    "title": c["title"],
                    "turn": c["turn"],
                    "loaded_files": c.get("loaded_files", []),
                    "messages": filtered_messages,
                })
            else:
                self._send_json(404, {"error": "Chat not found"})
            return

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
        from chatbot_ui import bot, manager

        if self.path == "/transcribe":
            filename, audio_data = parse_multipart(self.headers, self.rfile)
            if not audio_data:
                self._send_json(400, {"error": "No audio data received."})
                return
            try:
                text = transcribe_audio(bot.client, filename, audio_data)
                self._send_json(200, {"text": text})
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

            if needs_image(msg):
                prompt = extract_image_prompt(msg)
                image_url = generate_image_url(prompt)
                bot.turn += 1
                bot.history.append({"role": "user", "content": msg})
                reply = f"Here's your generated image! 🎨\n\n![{prompt}]({image_url})"
                bot.history.append({"role": "assistant", "content": reply})
                manager.auto_title(manager.active_id, msg)
                manager.save_after_message()
                self._send_json(200, {"reply": reply})
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
