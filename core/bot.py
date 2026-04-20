import os
import re
from datetime import datetime

from openai import OpenAI

from core.config import MODEL, SYSTEM_PROMPT
from search.web_search import _needs_search, _build_search_query, _is_search_followup, _web_search


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
        self.turn += 1

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
            search_q = user_message + " " + self.last_search_topic
            ctx = _web_search(search_q)
            if ctx:
                enriched = ctx + "\n\n" + user_message
        else:
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
