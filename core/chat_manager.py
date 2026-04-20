import json
import os
import time
import uuid

from core.config import STORE_PATH, SYSTEM_PROMPT


class ChatManager:
    def __init__(self, bot_instance, store_path=STORE_PATH):
        self.bot = bot_instance
        self.store_path = store_path
        self.chats = {}
        self.active_id = None
        self._load()
        if not self.chats:
            self.new_chat()

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

    def _serialize_history(self, history):
        """Convert history with tool_calls objects to JSON-serializable format."""
        serialized = []
        for msg in history:
            msg_copy = msg.copy()
            
            # Handle tool_calls field if present
            if "tool_calls" in msg_copy and msg_copy["tool_calls"]:
                # tool_calls is already a list of dicts from our code, just ensure it's serializable
                tool_calls_list = []
                for tc in msg_copy["tool_calls"]:
                    if isinstance(tc, dict):
                        tool_calls_list.append(tc)
                    else:
                        # If it's an object, convert to dict
                        tool_calls_list.append({
                            "id": tc.get("id", ""),
                            "type": tc.get("type", "function"),
                            "function": tc.get("function", {})
                        })
                msg_copy["tool_calls"] = tool_calls_list
            
            serialized.append(msg_copy)
        return serialized

    def _save(self):
        self._snapshot_current()
        data = {"active": self.active_id, "chats": self.chats}
        with open(self.store_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _snapshot_current(self):
        if self.active_id and self.active_id in self.chats:
            chat = self.chats[self.active_id]
            # Serialize history to ensure tool_calls are JSON-compatible
            chat["history"] = self._serialize_history(self.bot.history)
            chat["turn"] = self.bot.turn
            chat["loaded_files"] = self.bot.loaded_files

    def _apply_chat(self, chat_id):
        chat = self.chats[chat_id]
        self.bot.history = chat["history"]
        self.bot.turn = chat["turn"]
        self.bot.loaded_files = chat.get("loaded_files", [])
        self.active_id = chat_id

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
